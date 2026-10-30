"""
Database constraint tests for the GitHub repository models (ADR-017).

Isolation strategy: each test runs inside a transaction that is rolled
back at teardown by the db_session fixture. The alembic migration is
applied once per session by db_engine. The dev database is never touched.
"""

import itertools

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models.github import GitHubRepository, ProjectRepository
from app.models.identity import Profile, User
from app.models.projects import Project

_ids = itertools.count(950_001)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _owner(db_session) -> User:
    """A user with a profile; both flushed."""
    n = next(_ids)
    user = User(github_user_id=n, github_login=f"owner{n}")
    db_session.add(user)
    db_session.flush()
    db_session.add(Profile(user_id=user.id, slug=f"owner{n}", status="PRIVATE"))
    db_session.flush()
    return user


def _project(db_session, owner: User) -> Project:
    project = Project(owner_id=owner.id)
    db_session.add(project)
    db_session.flush()
    return project


def _repository_fields(**overrides) -> dict:
    n = next(_ids)
    fields = {
        "github_repo_id": n,
        "owner_github_id": n,
        "owner_login": "octo",
        "name": f"repo{n}",
        "is_fork": False,
        "is_archived": False,
    }
    fields.update(overrides)
    fields.setdefault("full_name", f"{fields['owner_login']}/{fields['name']}")
    fields.setdefault("html_url", f"https://github.com/{fields['full_name']}")
    return fields


def _repository(db_session, **overrides) -> GitHubRepository:
    repository = GitHubRepository(**_repository_fields(**overrides))
    db_session.add(repository)
    db_session.flush()
    return repository


def _link(
    db_session, project: Project, repository: GitHubRepository, relation: str = "OWNER"
) -> ProjectRepository:
    link = ProjectRepository(
        project_id=project.id,
        owner_id=project.owner_id,
        github_repository_id=repository.id,
        relation=relation,
    )
    db_session.add(link)
    db_session.flush()
    return link


def _flush_violates(db_session, constraint: str) -> None:
    with pytest.raises(IntegrityError) as exc:
        db_session.flush()
    assert exc.value.orig.diag.constraint_name == constraint


def _count(db_session, sql: str, **params) -> int:
    return db_session.execute(text(sql), params).scalar_one()


# ---------------------------------------------------------------------------
# github_repositories
# ---------------------------------------------------------------------------


def test_repository_defaults(db_session):
    repository = _repository(db_session)
    db_session.refresh(repository)

    assert repository.description is None
    assert repository.parent_full_name is None
    assert repository.pushed_at is None
    assert repository.languages is None
    assert repository.unavailable_since is None
    assert repository.created_at is not None
    assert repository.updated_at is not None


def test_repository_accepts_languages_object(db_session):
    repository = _repository(db_session, languages={"Python": 120_000, "HTML": 300})
    db_session.refresh(repository)

    assert repository.languages == {"Python": 120_000, "HTML": 300}


def test_github_repo_id_is_unique(db_session):
    first = _repository(db_session)
    db_session.add(GitHubRepository(**_repository_fields(github_repo_id=first.github_repo_id)))

    _flush_violates(db_session, "github_repositories_github_repo_id_key")


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"owner_login": " "}, "ck_github_repositories_names"),
        ({"name": ""}, "ck_github_repositories_names"),
        ({"full_name": "someone/else"}, "ck_github_repositories_full_name"),
        ({"html_url": "http://github.com/octo/repo"}, "ck_github_repositories_html_url"),
        ({"html_url": "https://github.com.evil.example/x"}, "ck_github_repositories_html_url"),
        ({"html_url": "https://example.com/octo/repo"}, "ck_github_repositories_html_url"),
        ({"languages": ["Python"]}, "ck_github_repositories_languages"),
        ({"languages": 42}, "ck_github_repositories_languages"),
    ],
)
def test_repository_checks(db_session, overrides, constraint):
    db_session.add(GitHubRepository(**_repository_fields(**overrides)))

    _flush_violates(db_session, constraint)


# ---------------------------------------------------------------------------
# project_repositories
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relation", ["OWNER", "CONTRIBUTOR", "NONE"])
def test_link_accepts_each_relation(db_session, relation):
    owner = _owner(db_session)
    link = _link(db_session, _project(db_session, owner), _repository(db_session), relation)
    db_session.refresh(link)

    assert link.relation == relation
    assert link.relation_checked_at is not None
    assert link.created_at is not None


@pytest.mark.parametrize("relation", ["owner", "MEMBER", ""])
def test_link_rejects_unknown_relation(db_session, relation):
    owner = _owner(db_session)
    project = _project(db_session, owner)
    db_session.add(
        ProjectRepository(
            project_id=project.id,
            owner_id=owner.id,
            github_repository_id=_repository(db_session).id,
            relation=relation,
        )
    )

    _flush_violates(db_session, "ck_project_repositories_relation")


def test_project_links_one_repository(db_session):
    owner = _owner(db_session)
    project = _project(db_session, owner)
    _link(db_session, project, _repository(db_session))
    db_session.add(
        ProjectRepository(
            project_id=project.id,
            owner_id=owner.id,
            github_repository_id=_repository(db_session).id,
            relation="OWNER",
        )
    )

    _flush_violates(db_session, "project_repositories_project_id_key")


def test_user_links_a_repository_to_one_project_only(db_session):
    owner = _owner(db_session)
    repository = _repository(db_session)
    _link(db_session, _project(db_session, owner), repository)
    second = _project(db_session, owner)
    db_session.add(
        ProjectRepository(
            project_id=second.id,
            owner_id=owner.id,
            github_repository_id=repository.id,
            relation="OWNER",
        )
    )

    _flush_violates(db_session, "uq_project_repositories_owner_repository")


def test_two_users_link_the_same_repository(db_session):
    repository = _repository(db_session)
    _link(db_session, _project(db_session, _owner(db_session)), repository, "OWNER")
    _link(db_session, _project(db_session, _owner(db_session)), repository, "CONTRIBUTOR")

    assert (
        _count(
            db_session,
            "SELECT count(*) FROM project_repositories WHERE github_repository_id = :id",
            id=repository.id,
        )
        == 2
    )


def test_link_owner_must_be_project_owner(db_session):
    project = _project(db_session, _owner(db_session))
    stranger = _owner(db_session)
    db_session.add(
        ProjectRepository(
            project_id=project.id,
            owner_id=stranger.id,
            github_repository_id=_repository(db_session).id,
            relation="OWNER",
        )
    )

    _flush_violates(db_session, "project_repositories_project_id_owner_id_fkey")


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------


def test_deleting_project_removes_link_and_keeps_repository(db_session):
    """Raw SQL DELETE bypasses the ORM: checks the database-level cascade."""
    project = _project(db_session, _owner(db_session))
    repository = _repository(db_session)
    _link(db_session, project, repository)

    db_session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project.id})

    assert (
        _count(
            db_session,
            "SELECT count(*) FROM project_repositories WHERE project_id = :id",
            id=project.id,
        )
        == 0
    )
    assert _count(
        db_session, "SELECT count(*) FROM github_repositories WHERE id = :id", id=repository.id
    )


def test_deleting_user_removes_links_and_keeps_repository(db_session):
    owner = _owner(db_session)
    repository = _repository(db_session)
    _link(db_session, _project(db_session, owner), repository)
    other = _link(db_session, _project(db_session, _owner(db_session)), repository)

    db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": owner.id})

    remaining = db_session.scalars(
        select(ProjectRepository.id).where(ProjectRepository.github_repository_id == repository.id)
    ).all()
    assert remaining == [other.id]
    assert _count(
        db_session, "SELECT count(*) FROM github_repositories WHERE id = :id", id=repository.id
    )


def test_linked_repository_cannot_be_deleted(db_session):
    repository = _repository(db_session)
    _link(db_session, _project(db_session, _owner(db_session)), repository)

    with pytest.raises(IntegrityError) as exc:
        db_session.execute(
            text("DELETE FROM github_repositories WHERE id = :id"), {"id": repository.id}
        )
    assert exc.value.orig.diag.constraint_name == "project_repositories_github_repository_id_fkey"


def test_unlinked_repository_can_be_deleted(db_session):
    repository = _repository(db_session)

    db_session.execute(
        text("DELETE FROM github_repositories WHERE id = :id"), {"id": repository.id}
    )

    assert not _count(
        db_session, "SELECT count(*) FROM github_repositories WHERE id = :id", id=repository.id
    )
