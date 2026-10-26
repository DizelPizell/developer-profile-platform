import uuid
from datetime import UTC, datetime

from sqlalchemy import bindparam, delete, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import ARRAY, TEXT
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models.identity import Profile, User
from app.models.projects import (
    PROJECT_PUBLISH_REQUIRED,
    Project,
    ProjectShowcase,
    ProjectTechnology,
    Technology,
)

DRAFT = "DRAFT"
PUBLISHED = "PUBLISHED"
ARCHIVED = "ARCHIVED"
PUBLIC = "PUBLIC"
PRIVATE = "PRIVATE"

MAX_PROJECTS_PER_USER = 50

# Technology ids for names, in input order, matched with the database's lower()
# so the lookup agrees with the uq_technologies_name_lower index.
_TECHNOLOGY_IDS = text(
    "SELECT t.id FROM unnest(:names) WITH ORDINALITY AS n(name, ord) "
    "JOIN technologies t ON lower(t.name) = lower(n.name) ORDER BY n.ord"
).bindparams(bindparam("names", type_=ARRAY(TEXT)))


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _not_found() -> AppError:
    # A foreign, missing or malformed id is indistinguishable from an unknown URL.
    return AppError("NOT_FOUND", "Not Found", 404)


def _incomplete(missing: list[str]) -> AppError:
    return AppError(
        "PROJECT_INCOMPLETE",
        "Project is missing fields required for publication",
        422,
        {"missing_fields": missing},
    )


def _transition_invalid(project: Project) -> AppError:
    return AppError(
        "PROJECT_TRANSITION_INVALID",
        "Action is not allowed in the current project state",
        409,
        {"status": project.status},
    )


def _duplicate_technologies() -> AppError:
    # Same shape as a request validation error: two names the database treats as one.
    return AppError(
        "VALIDATION_ERROR",
        "Invalid request",
        422,
        {"fields": [{"loc": ["body", "technologies"], "type": "duplicate_technology"}]},
    )


def _missing_for_publication(values: dict[str, str | None], technology_count: int) -> list[str]:
    missing = [field for field in PROJECT_PUBLISH_REQUIRED if values.get(field) is None]
    if technology_count == 0:
        missing.append("technologies")
    return missing


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def lock_owner_profile(db: Session, user: User) -> Profile:
    """Locks the owner's profile row. Taken before any project row (ADR-015) by
    operations that check the project limit or change featured projects."""
    return db.execute(
        select(Profile).where(Profile.user_id == user.id).with_for_update()
    ).scalar_one()


def get_own_project(
    db: Session, user: User, project_id: str, *, for_update: bool = False
) -> Project:
    try:
        parsed_id = uuid.UUID(project_id)
    except ValueError:
        raise _not_found() from None
    stmt = select(Project).where(Project.id == parsed_id, Project.owner_id == user.id)
    if for_update:
        stmt = stmt.with_for_update()
    project = db.execute(stmt).scalar_one_or_none()
    if project is None:
        raise _not_found()
    return project


def list_own_projects(db: Session, user: User) -> list[Project]:
    stmt = (
        select(Project)
        .where(Project.owner_id == user.id)
        .order_by(Project.created_at.desc(), Project.id.desc())
    )
    return list(db.execute(stmt).scalars())


def technology_names(db: Session, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    """Technology names per project, in the developer's order."""
    rows = db.execute(
        select(ProjectTechnology.project_id, Technology.name)
        .join(Technology, Technology.id == ProjectTechnology.technology_id)
        .where(ProjectTechnology.project_id.in_(project_ids))
        .order_by(ProjectTechnology.project_id, ProjectTechnology.position)
    )
    names: dict[uuid.UUID, list[str]] = {project_id: [] for project_id in project_ids}
    for project_id, name in rows:
        names[project_id].append(name)
    return names


def featured_positions(db: Session, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    rows = db.execute(
        select(ProjectShowcase.project_id, ProjectShowcase.position).where(
            ProjectShowcase.project_id.in_(project_ids)
        )
    )
    return {project_id: position for project_id, position in rows}


def _technology_ids(db: Session, project: Project) -> list[uuid.UUID]:
    return list(
        db.execute(
            select(ProjectTechnology.technology_id)
            .where(ProjectTechnology.project_id == project.id)
            .order_by(ProjectTechnology.position)
        ).scalars()
    )


# ---------------------------------------------------------------------------
# Technologies
# ---------------------------------------------------------------------------


def _resolve_technologies(db: Session, names: list[str]) -> list[uuid.UUID]:
    """Get or create technologies by name, ignoring case; ids in the given order.

    INSERT ... ON CONFLICT DO NOTHING on the lower(name) index: a concurrent insert of
    the same name waits for the other transaction and then skips, so there is no
    unique-violation race. Rows are inserted sorted by lower(name), so two requests
    with overlapping names lock them in the same order and cannot deadlock.
    """
    if not names:
        return []
    db.execute(
        pg_insert(Technology)
        .values([{"name": name} for name in sorted(names, key=str.lower)])
        .on_conflict_do_nothing(index_elements=[func.lower(Technology.name)])
    )
    # A new statement: in READ COMMITTED it also sees rows committed by the
    # concurrent transaction we waited for.
    ids = list(db.execute(_TECHNOLOGY_IDS, {"names": names}).scalars())
    if len(set(ids)) != len(names):
        # Names that Python's lower() keeps apart but PostgreSQL's lower() does not.
        raise _duplicate_technologies()
    return ids


def _replace_technologies(db: Session, project: Project, technology_ids: list[uuid.UUID]) -> None:
    db.execute(delete(ProjectTechnology).where(ProjectTechnology.project_id == project.id))
    if technology_ids:
        db.execute(
            insert(ProjectTechnology),
            [
                {"project_id": project.id, "technology_id": technology_id, "position": position}
                for position, technology_id in enumerate(technology_ids, start=1)
            ],
        )


# ---------------------------------------------------------------------------
# Featured projects
# ---------------------------------------------------------------------------


def _remove_from_featured(db: Session, project: Project) -> None:
    """Removes the project's showcase row and closes the gap with one UPDATE.

    The caller holds the owner's profile lock. UNIQUE (profile_id, position) is
    DEFERRABLE INITIALLY IMMEDIATE, so the shift is checked at the end of the statement.
    """
    removed = db.execute(
        delete(ProjectShowcase)
        .where(ProjectShowcase.project_id == project.id)
        .returning(ProjectShowcase.profile_id, ProjectShowcase.position)
    ).first()
    if removed is None:
        return
    profile_id, position = removed
    db.execute(
        update(ProjectShowcase)
        .where(ProjectShowcase.profile_id == profile_id, ProjectShowcase.position > position)
        .values(position=ProjectShowcase.position - 1)
    )


# ---------------------------------------------------------------------------
# Changes
# ---------------------------------------------------------------------------


def create_project(
    db: Session,
    user: User,
    changes: dict[str, str | None],
    technologies: list[str] | None,
) -> Project:
    """The caller holds the owner's profile lock, so the count below is stable."""
    count = db.execute(
        select(func.count()).select_from(Project).where(Project.owner_id == user.id)
    ).scalar_one()
    if count >= MAX_PROJECTS_PER_USER:
        raise AppError(
            "PROJECT_LIMIT_REACHED",
            "Project limit reached",
            409,
            {"limit": MAX_PROJECTS_PER_USER},
        )
    now = _utcnow()
    # Timestamps from the application, not now(): they differ between projects
    # created in one transaction, which keeps "newest first" well defined.
    project = Project(
        owner_id=user.id,
        status=DRAFT,
        visibility=PRIVATE,
        created_at=now,
        updated_at=now,
        **changes,
    )
    db.add(project)
    db.flush()
    if technologies:
        _replace_technologies(db, project, _resolve_technologies(db, technologies))
    return project


def update_project(
    db: Session,
    project: Project,
    changes: dict[str, str | None],
    technologies: list[str] | None,
) -> None:
    """The caller holds the project row lock."""
    current_ids = _technology_ids(db, project)
    if project.status == PUBLISHED:
        resulting = {f: changes.get(f, getattr(project, f)) for f in PROJECT_PUBLISH_REQUIRED}
        count = len(technologies) if technologies is not None else len(current_ids)
        missing = _missing_for_publication(resulting, count)
        if missing:
            raise _incomplete(missing)

    changed = False
    for field, value in changes.items():
        if getattr(project, field) != value:
            setattr(project, field, value)
            changed = True
    if technologies is not None:
        new_ids = _resolve_technologies(db, technologies)
        if new_ids != current_ids:
            _replace_technologies(db, project, new_ids)
            changed = True
    if changed:
        project.updated_at = _utcnow()
        db.flush()


def publish(db: Session, project: Project) -> None:
    """DRAFT or ARCHIVED → PUBLISHED + PUBLIC; already PUBLISHED is a no-op."""
    if project.status == PUBLISHED:
        return
    missing = _missing_for_publication(
        {f: getattr(project, f) for f in PROJECT_PUBLISH_REQUIRED},
        len(_technology_ids(db, project)),
    )
    if missing:
        raise _incomplete(missing)
    project.status = PUBLISHED
    project.visibility = PUBLIC
    project.updated_at = _utcnow()
    db.flush()


def archive(db: Session, project: Project) -> None:
    """PUBLISHED → ARCHIVED + PRIVATE; removes it from featured projects.

    The caller holds the owner's profile lock, then the project row lock.
    """
    if project.status == ARCHIVED:
        return
    if project.status != PUBLISHED:
        raise _transition_invalid(project)
    _remove_from_featured(db, project)
    project.status = ARCHIVED
    project.visibility = PRIVATE
    project.updated_at = _utcnow()
    db.flush()


def change_visibility(db: Session, project: Project, visibility: str) -> None:
    """Only while PUBLISHED; hiding removes it from featured projects.

    The caller holds the owner's profile lock, then the project row lock.
    """
    if project.status != PUBLISHED:
        raise _transition_invalid(project)
    if project.visibility == visibility:
        return
    if visibility == PRIVATE:
        _remove_from_featured(db, project)
    project.visibility = visibility
    project.updated_at = _utcnow()
    db.flush()


def delete_project(db: Session, project: Project) -> None:
    """Hard delete; showcase and technology links go by cascade, the featured gap is closed.

    The caller holds the owner's profile lock, then the project row lock.
    """
    _remove_from_featured(db, project)
    db.delete(project)
    db.flush()
