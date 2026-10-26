"""
Database constraint tests for the project models (ADR-015).

Isolation strategy: each test runs inside a transaction that is rolled
back at teardown by the db_session fixture. The alembic migration is
applied once per session by db_engine. The dev database is never touched.
"""

import itertools

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.identity import Profile, User
from app.models.projects import (
    PROJECT_TEXT_LIMITS,
    Project,
    ProjectShowcase,
    ProjectTechnology,
    Technology,
)

_ids = itertools.count(900_001)

_COMPLETE = {
    "title": "Title",
    "summary": "Summary",
    "role": "Backend",
    "contribution": "Built the API",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _owner(db_session) -> tuple[User, Profile]:
    """A user with a profile; both flushed."""
    n = next(_ids)
    user = User(github_user_id=n, github_login=f"owner{n}")
    db_session.add(user)
    db_session.flush()
    profile = Profile(user_id=user.id, slug=f"owner{n}", status="PRIVATE")
    db_session.add(profile)
    db_session.flush()
    return user, profile


def _project(db_session, owner: User, **fields) -> Project:
    project = Project(owner_id=owner.id, **fields)
    db_session.add(project)
    db_session.flush()
    return project


def _published(db_session, owner: User) -> Project:
    return _project(db_session, owner, status="PUBLISHED", visibility="PUBLIC", **_COMPLETE)


def _technology(db_session, name: str) -> Technology:
    technology = Technology(name=name)
    db_session.add(technology)
    db_session.flush()
    return technology


def _flush_violates(db_session, constraint: str) -> None:
    with pytest.raises(IntegrityError) as exc:
        db_session.flush()
    assert exc.value.orig.diag.constraint_name == constraint


def _count(db_session, sql: str, **params) -> int:
    return db_session.execute(text(sql), params).scalar_one()


# ---------------------------------------------------------------------------
# projects: state pairs
# ---------------------------------------------------------------------------


def test_new_project_is_draft_and_private(db_session):
    owner, _ = _owner(db_session)
    project = _project(db_session, owner)
    db_session.refresh(project)

    assert (project.status, project.visibility) == ("DRAFT", "PRIVATE")
    assert project.title is None


@pytest.mark.parametrize(
    ("status", "visibility"),
    [
        ("DRAFT", "PRIVATE"),
        ("PUBLISHED", "PUBLIC"),
        ("PUBLISHED", "PRIVATE"),
        ("ARCHIVED", "PRIVATE"),
    ],
)
def test_allowed_state_pairs_accepted(db_session, status, visibility):
    owner, _ = _owner(db_session)
    _project(db_session, owner, status=status, visibility=visibility, **_COMPLETE)


@pytest.mark.parametrize(
    ("status", "visibility"),
    [
        ("DRAFT", "PUBLIC"),
        ("ARCHIVED", "PUBLIC"),
        ("ACTIVE", "PRIVATE"),
        ("PUBLISHED", "HIDDEN"),
        ("draft", "private"),
    ],
)
def test_invalid_state_pairs_rejected(db_session, status, visibility):
    owner, _ = _owner(db_session)
    db_session.add(Project(owner_id=owner.id, status=status, visibility=visibility, **_COMPLETE))
    _flush_violates(db_session, "ck_projects_state")


# ---------------------------------------------------------------------------
# projects: text fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("field", "limit"), PROJECT_TEXT_LIMITS.items())
def test_text_field_at_limit_accepted(db_session, field, limit):
    owner, _ = _owner(db_session)
    _project(db_session, owner, **{field: "x" * limit})


@pytest.mark.parametrize(("field", "limit"), PROJECT_TEXT_LIMITS.items())
def test_text_field_over_limit_rejected(db_session, field, limit):
    owner, _ = _owner(db_session)
    db_session.add(Project(owner_id=owner.id, **{field: "x" * (limit + 1)}))
    _flush_violates(db_session, f"ck_projects_{field}")


@pytest.mark.parametrize("value", ["", "   "])
@pytest.mark.parametrize("field", PROJECT_TEXT_LIMITS)
def test_text_field_blank_rejected(db_session, field, value):
    owner, _ = _owner(db_session)
    db_session.add(Project(owner_id=owner.id, **{field: value}))
    _flush_violates(db_session, f"ck_projects_{field}")


def test_newline_only_value_passes_database_check(db_session):
    """btrim() strips only spaces, as for profiles (ADR-013): a newline-only value
    is stopped by normalization in the application, not by the database."""
    owner, _ = _owner(db_session)
    _project(db_session, owner, description="\n")


def test_length_is_counted_in_characters(db_session):
    owner, _ = _owner(db_session)
    _project(db_session, owner, title="я" * 100)  # 200 bytes, 100 characters


@pytest.mark.parametrize("missing", ["title", "summary", "role", "contribution"])
def test_published_project_requires_text_fields(db_session, missing):
    owner, _ = _owner(db_session)
    fields = {**_COMPLETE, missing: None}
    db_session.add(Project(owner_id=owner.id, status="PUBLISHED", visibility="PUBLIC", **fields))
    _flush_violates(db_session, "ck_projects_published_complete")


@pytest.mark.parametrize(
    ("status", "visibility"),
    [("DRAFT", "PRIVATE"), ("ARCHIVED", "PRIVATE")],
)
def test_unpublished_project_may_be_incomplete(db_session, status, visibility):
    owner, _ = _owner(db_session)
    _project(db_session, owner, status=status, visibility=visibility)


def test_description_problem_results_not_required_to_publish(db_session):
    owner, _ = _owner(db_session)
    project = _published(db_session, owner)
    assert project.description is None and project.problem is None and project.results is None


# ---------------------------------------------------------------------------
# technologies
# ---------------------------------------------------------------------------


def test_technology_name_at_limit_accepted(db_session):
    _technology(db_session, "x" * 50)


def test_technology_name_over_limit_rejected(db_session):
    db_session.add(Technology(name="x" * 51))
    _flush_violates(db_session, "ck_technologies_name")


@pytest.mark.parametrize("name", ["", "   "])
def test_technology_name_blank_rejected(db_session, name):
    db_session.add(Technology(name=name))
    _flush_violates(db_session, "ck_technologies_name")


@pytest.mark.parametrize("duplicate", ["python", "PYTHON", "PyThOn"])
def test_technology_name_unique_ignoring_case(db_session, duplicate):
    _technology(db_session, "Python")
    db_session.add(Technology(name=duplicate))
    _flush_violates(db_session, "uq_technologies_name_lower")


def test_technology_names_with_symbols_accepted(db_session):
    for name in ("C#", "C++", "Node.js", "ASP.NET Core", "Вёрстка"):
        _technology(db_session, name)


# ---------------------------------------------------------------------------
# project_technologies
# ---------------------------------------------------------------------------


def test_same_technology_twice_in_project_rejected(db_session):
    owner, _ = _owner(db_session)
    project = _project(db_session, owner)
    technology = _technology(db_session, "Go")
    db_session.add(
        ProjectTechnology(project_id=project.id, technology_id=technology.id, position=1)
    )
    db_session.flush()

    db_session.add(
        ProjectTechnology(project_id=project.id, technology_id=technology.id, position=2)
    )
    _flush_violates(db_session, "uq_project_technologies_technology")


def test_same_position_twice_in_project_rejected(db_session):
    owner, _ = _owner(db_session)
    project = _project(db_session, owner)
    go = _technology(db_session, "Go")
    rust = _technology(db_session, "Rust")
    db_session.add(ProjectTechnology(project_id=project.id, technology_id=go.id, position=1))
    db_session.flush()

    db_session.add(ProjectTechnology(project_id=project.id, technology_id=rust.id, position=1))
    _flush_violates(db_session, "uq_project_technologies_position")


def test_same_technology_in_two_projects_accepted(db_session):
    owner, _ = _owner(db_session)
    first = _project(db_session, owner)
    second = _project(db_session, owner)
    technology = _technology(db_session, "Go")
    db_session.add_all(
        [
            ProjectTechnology(project_id=first.id, technology_id=technology.id, position=1),
            ProjectTechnology(project_id=second.id, technology_id=technology.id, position=1),
        ]
    )
    db_session.flush()


@pytest.mark.parametrize("position", [1, 20])
def test_technology_position_in_range_accepted(db_session, position):
    owner, _ = _owner(db_session)
    project = _project(db_session, owner)
    technology = _technology(db_session, "Go")
    db_session.add(
        ProjectTechnology(project_id=project.id, technology_id=technology.id, position=position)
    )
    db_session.flush()


@pytest.mark.parametrize("position", [0, 21])
def test_technology_position_out_of_range_rejected(db_session, position):
    owner, _ = _owner(db_session)
    project = _project(db_session, owner)
    technology = _technology(db_session, "Go")
    db_session.add(
        ProjectTechnology(project_id=project.id, technology_id=technology.id, position=position)
    )
    _flush_violates(db_session, "ck_project_technologies_position")


def test_technology_positions_cannot_be_swapped_in_one_update(db_session):
    """The technology order is replaced by delete and insert (ADR-015): its unique
    constraint is immediate, so an in-place swap fails, unlike project_showcases."""
    owner, _ = _owner(db_session)
    project = _project(db_session, owner)
    go = _technology(db_session, "Go")
    rust = _technology(db_session, "Rust")
    db_session.add_all(
        [
            ProjectTechnology(project_id=project.id, technology_id=go.id, position=1),
            ProjectTechnology(project_id=project.id, technology_id=rust.id, position=2),
        ]
    )
    db_session.flush()

    with pytest.raises(IntegrityError) as exc:
        db_session.execute(
            text(
                "UPDATE project_technologies SET position = 3 - position "
                "WHERE project_id = :project_id"
            ),
            {"project_id": project.id},
        )
    assert exc.value.orig.diag.constraint_name == "uq_project_technologies_position"


# ---------------------------------------------------------------------------
# project_showcases
# ---------------------------------------------------------------------------


def _feature(db_session, project: Project, profile: Profile, position: int) -> None:
    db_session.add(ProjectShowcase(project_id=project.id, profile_id=profile.id, position=position))


def _positions(db_session, profile: Profile) -> dict:
    rows = db_session.execute(
        text("SELECT project_id, position FROM project_showcases WHERE profile_id = :profile_id"),
        {"profile_id": profile.id},
    )
    return {project_id: position for project_id, position in rows}


@pytest.mark.parametrize("position", [1, 2, 3])
def test_showcase_position_in_range_accepted(db_session, position):
    owner, profile = _owner(db_session)
    _feature(db_session, _published(db_session, owner), profile, position)
    db_session.flush()


@pytest.mark.parametrize("position", [0, 4])
def test_showcase_position_out_of_range_rejected(db_session, position):
    owner, profile = _owner(db_session)
    _feature(db_session, _published(db_session, owner), profile, position)
    _flush_violates(db_session, "ck_project_showcases_position")


def test_project_featured_only_once(db_session):
    owner, profile = _owner(db_session)
    project = _published(db_session, owner)
    _feature(db_session, project, profile, 1)
    db_session.flush()

    _feature(db_session, project, profile, 2)
    _flush_violates(db_session, "project_showcases_project_id_key")


def test_showcase_position_unique_per_profile(db_session):
    owner, profile = _owner(db_session)
    _feature(db_session, _published(db_session, owner), profile, 1)
    db_session.flush()

    _feature(db_session, _published(db_session, owner), profile, 1)
    _flush_violates(db_session, "uq_project_showcases_position")


def test_same_position_on_two_profiles_accepted(db_session):
    first_owner, first_profile = _owner(db_session)
    second_owner, second_profile = _owner(db_session)
    _feature(db_session, _published(db_session, first_owner), first_profile, 1)
    _feature(db_session, _published(db_session, second_owner), second_profile, 1)
    db_session.flush()


def test_fourth_featured_project_cannot_be_stored(db_session):
    owner, profile = _owner(db_session)
    for position in (1, 2, 3):
        _feature(db_session, _published(db_session, owner), profile, position)
    db_session.flush()

    # Every free position is outside the range, every position in range is taken.
    _feature(db_session, _published(db_session, owner), profile, 4)
    _flush_violates(db_session, "ck_project_showcases_position")


def test_showcase_positions_swapped_in_one_update(db_session):
    owner, profile = _owner(db_session)
    first = _published(db_session, owner)
    second = _published(db_session, owner)
    _feature(db_session, first, profile, 1)
    _feature(db_session, second, profile, 2)
    db_session.flush()

    db_session.execute(
        text(
            "UPDATE project_showcases "
            "SET position = CASE position WHEN 1 THEN 2 WHEN 2 THEN 1 END "
            "WHERE profile_id = :profile_id"
        ),
        {"profile_id": profile.id},
    )

    assert _positions(db_session, profile) == {first.id: 2, second.id: 1}


def test_showcase_gap_closed_in_one_update(db_session):
    owner, profile = _owner(db_session)
    second = _published(db_session, owner)
    third = _published(db_session, owner)
    _feature(db_session, second, profile, 2)
    _feature(db_session, third, profile, 3)
    db_session.flush()

    db_session.execute(
        text("UPDATE project_showcases SET position = position - 1 WHERE profile_id = :profile_id"),
        {"profile_id": profile.id},
    )

    assert _positions(db_session, profile) == {second.id: 1, third.id: 2}


def test_showcase_duplicate_position_rejected_at_statement_end(db_session):
    """Deferrable INITIALLY IMMEDIATE still rejects a duplicate left by a statement."""
    owner, profile = _owner(db_session)
    _feature(db_session, _published(db_session, owner), profile, 1)
    _feature(db_session, _published(db_session, owner), profile, 2)
    db_session.flush()

    with pytest.raises(IntegrityError) as exc:
        db_session.execute(
            text("UPDATE project_showcases SET position = 1 WHERE profile_id = :profile_id"),
            {"profile_id": profile.id},
        )
    assert exc.value.orig.diag.constraint_name == "uq_project_showcases_position"


# ---------------------------------------------------------------------------
# ON DELETE
# ---------------------------------------------------------------------------


def _project_with_links(db_session) -> tuple[User, Profile, Project, Technology]:
    owner, profile = _owner(db_session)
    project = _published(db_session, owner)
    technology = _technology(db_session, f"Tech {next(_ids)}")
    db_session.add(
        ProjectTechnology(project_id=project.id, technology_id=technology.id, position=1)
    )
    _feature(db_session, project, profile, 1)
    db_session.flush()
    return owner, profile, project, technology


def test_deleting_user_removes_projects_showcases_and_links(db_session):
    """Raw SQL DELETE bypasses the ORM: checks the database-level cascades."""
    owner, _, project, technology = _project_with_links(db_session)

    db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": owner.id})

    assert (
        _count(db_session, "SELECT count(*) FROM projects WHERE owner_id = :id", id=owner.id) == 0
    )
    for table in ("project_showcases", "project_technologies"):
        count = _count(
            db_session,
            f"SELECT count(*) FROM {table} WHERE project_id = :id",  # noqa: S608
            id=project.id,
        )
        assert count == 0, f"Expected {table} rows to be CASCADE-deleted, found {count}"
    assert _count(db_session, "SELECT count(*) FROM technologies WHERE id = :id", id=technology.id)


def test_deleting_project_removes_showcase_and_links_but_not_technologies(db_session):
    owner, _, project, technology = _project_with_links(db_session)
    other = _project(db_session, owner)
    db_session.add(ProjectTechnology(project_id=other.id, technology_id=technology.id, position=1))
    db_session.flush()

    db_session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project.id})

    for table in ("project_showcases", "project_technologies"):
        count = _count(
            db_session,
            f"SELECT count(*) FROM {table} WHERE project_id = :id",  # noqa: S608
            id=project.id,
        )
        assert count == 0, f"Expected {table} rows to be CASCADE-deleted, found {count}"
    assert _count(db_session, "SELECT count(*) FROM technologies WHERE id = :id", id=technology.id)
    assert _count(
        db_session, "SELECT count(*) FROM project_technologies WHERE project_id = :id", id=other.id
    )


def test_deleting_profile_removes_showcase_but_not_project(db_session):
    _, profile, project, _ = _project_with_links(db_session)

    db_session.execute(text("DELETE FROM profiles WHERE id = :id"), {"id": profile.id})

    assert not _count(
        db_session, "SELECT count(*) FROM project_showcases WHERE project_id = :id", id=project.id
    )
    assert _count(db_session, "SELECT count(*) FROM projects WHERE id = :id", id=project.id)


def test_deleting_used_technology_is_restricted(db_session):
    _, _, _, technology = _project_with_links(db_session)

    with pytest.raises(IntegrityError) as exc:
        db_session.execute(text("DELETE FROM technologies WHERE id = :id"), {"id": technology.id})
    assert exc.value.orig.diag.constraint_name == "project_technologies_technology_id_fkey"
