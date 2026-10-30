import uuid
from datetime import UTC, datetime

from sqlalchemy import Row, bindparam, case, delete, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import ARRAY, TEXT
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.canonical_uuid import parse_canonical_uuid
from app.errors import AppError
from app.github import service as github_service
from app.models.identity import Profile, User
from app.models.projects import (
    FEATURED_PROJECTS_PER_PROFILE,
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


def _not_featurable(project: Project) -> AppError:
    return AppError(
        "PROJECT_NOT_FEATURABLE",
        "Only a published public project can be featured",
        409,
        {"status": project.status, "visibility": project.visibility},
    )


def _featured_limit_reached() -> AppError:
    return AppError(
        "FEATURED_LIMIT_REACHED",
        "Featured project limit reached",
        409,
        {"limit": FEATURED_PROJECTS_PER_PROFILE},
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
    parsed_id = parse_canonical_uuid(project_id)
    if parsed_id is None:
        raise _not_found()
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


def featured_projects(db: Session, profile_id: uuid.UUID) -> list[tuple[uuid.UUID, int]]:
    """(project_id, position) of the profile's featured projects, in position order."""
    rows = db.execute(
        select(ProjectShowcase.project_id, ProjectShowcase.position)
        .where(ProjectShowcase.profile_id == profile_id)
        .order_by(ProjectShowcase.position)
    )
    return [(project_id, position) for project_id, position in rows]


def public_projects(db: Session, owner_id: uuid.UUID) -> list[Row]:
    """The owner's PUBLISHED + PUBLIC projects as (id, title, summary, role, position):
    featured ones first by position, then the others newest first (ADR-015).

    Only the public card's columns are read. position is None for a project that
    is not featured. The caller checks that the profile is published.
    """
    return list(
        db.execute(
            select(
                Project.id,
                Project.title,
                Project.summary,
                Project.role,
                ProjectShowcase.position,
            )
            .outerjoin(ProjectShowcase, ProjectShowcase.project_id == Project.id)
            .where(
                Project.owner_id == owner_id,
                Project.status == PUBLISHED,
                Project.visibility == PUBLIC,
            )
            .order_by(
                ProjectShowcase.position.asc().nulls_last(),
                Project.created_at.desc(),
                Project.id.desc(),
            )
        )
    )


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


def feature(db: Session, profile: Profile, project: Project) -> None:
    """Adds a PUBLISHED + PUBLIC project after the last featured one; already featured
    is a no-op.

    The caller holds the owner's profile lock, then the project row lock, so the
    count and max(position) below are stable. The limit itself is the database's:
    position is 1..3 and unique per profile, so a fourth row cannot be written even
    if this check were skipped. That violation is reported with the same code.
    """
    if project.status != PUBLISHED or project.visibility != PUBLIC:
        raise _not_featurable(project)
    current = featured_projects(db, profile.id)
    if any(project_id == project.id for project_id, _ in current):
        return
    if len(current) >= FEATURED_PROJECTS_PER_PROFILE:
        raise _featured_limit_reached()
    position = max((p for _, p in current), default=0) + 1
    try:
        # A savepoint keeps the transaction usable if the insert is rejected.
        with db.begin_nested():
            db.execute(
                insert(ProjectShowcase).values(
                    profile_id=profile.id, project_id=project.id, position=position
                )
            )
    except IntegrityError as exc:
        if getattr(exc.orig.diag, "constraint_name", None) == "ck_project_showcases_position":
            raise _featured_limit_reached() from None
        raise


def unfeature(db: Session, project: Project) -> None:
    """Not featured is a no-op. The caller holds the owner's profile lock."""
    _remove_from_featured(db, project)


def reorder_featured(db: Session, profile: Profile, project_ids: list[uuid.UUID]) -> None:
    """project_ids is the complete current featured set in the new order (unique,
    at most three: checked by the request schema).

    The caller holds the owner's profile lock, so the set compared here is the set
    updated. One UPDATE ... CASE: the deferrable UNIQUE (profile_id, position) is
    checked at the end of the statement, so swaps pass.
    """
    current = [project_id for project_id, _ in featured_projects(db, profile.id)]
    if set(project_ids) != set(current):
        raise AppError(
            "FEATURED_ORDER_MISMATCH",
            "The list does not match the current featured projects",
            409,
        )
    if project_ids == current:
        return
    new_positions = {project_id: i for i, project_id in enumerate(project_ids, start=1)}
    db.execute(
        update(ProjectShowcase)
        .where(ProjectShowcase.profile_id == profile.id)
        .values(position=case(new_positions, value=ProjectShowcase.project_id))
    )


# ---------------------------------------------------------------------------
# Changes
# ---------------------------------------------------------------------------


def check_project_limit(db: Session, user: User) -> None:
    """409 when the user has the maximum number of projects. Stable only under the
    owner's profile lock; without it, an early check that saves work."""
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


def create_project(
    db: Session,
    user: User,
    changes: dict[str, str | None],
    technologies: list[str] | None,
) -> Project:
    """The caller holds the owner's profile lock, so the limit check is stable."""
    check_project_limit(db, user)
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


def create_imported_project(
    db: Session, user: User, checked: github_service.CheckedRepository, now: datetime
) -> Project:
    """An import's write step (ADR-017): a DRAFT + PRIVATE project titled after the
    repository, with no other fields and no technologies, and its link, in the
    caller's transaction, so both are stored or neither. The profile lock is taken
    first, as on every project creation. Nothing is committed here."""
    lock_owner_profile(db, user)
    project = create_project(db, user, {"title": checked.data.name}, None)
    github_service.store_link(db, project, checked, now)
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
