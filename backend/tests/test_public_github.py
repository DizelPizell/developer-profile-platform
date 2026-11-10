"""`github` on public project cards (ADR-019, step 6.7): the whitelist, when it is null,
old data, shared repositories, and one more query for any number of projects, with no
GitHub call and no write."""

import json
from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, event, func, select, update
from sqlalchemy.orm import Session

from app.github import service as github_service
from app.github.budget import UserRequestBudget
from app.github.client import GitHubApiClient
from app.github.schemas import PublicGitHub
from app.models.github import (
    GitHubRepository,
    GitHubSyncCategoryStatus,
    GitHubSyncJob,
    ProjectRepository,
)
from tests.test_github_link_api import (
    GITHUB_ID,
    LOGIN,
    OTHER_GITHUB_ID,
    PROJECTS,
    STRANGER,
    STRANGER_ID,
    T0,
    Env,
    _create,
    _link,
    _new_client,
    _other_user,
    _repo,
    make_env,
)

PUBLIC = "/api/v1/public/profiles"
PUBLIC_GITHUB_KEYS = {
    "full_name",
    "html_url",
    "description",
    "languages",
    "pushed_at",
    "is_fork",
    "parent_full_name",
    "is_archived",
    "relation",
    "synced_at",
}
OLD = T0 - timedelta(days=30)
OLDER = T0 - timedelta(days=60)


@pytest.fixture
def env(make_auth_client, db_session: Session) -> Env:
    state = make_env(make_auth_client, db_session)
    _publish_profile(state.http)
    return state


@pytest.fixture
def visitor(env, make_auth_client):
    """No session, created after the owner so it shares the same database session."""
    return _new_client(make_auth_client, send_origin=False)


def _publish_profile(http) -> None:
    http.patch("/api/v1/profile", json={"display_name": "Ann", "headline": "Dev"})
    assert http.post("/api/v1/profile/publish").status_code == 200


def _slug(http) -> str:
    return http.get("/api/v1/profile").json()["slug"]


def _body(visitor, http) -> dict:
    resp = visitor.get(f"{PUBLIC}/{_slug(http)}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _cards(visitor, http) -> dict[str, dict]:
    body = _body(visitor, http)
    return {card["id"]: card for card in [*body["featured"], *body["other"]]}


def _card_github(visitor, http, project_id: str) -> dict | None:
    return _cards(visitor, http)[project_id]["github"]


def _published(http, **fields) -> str:
    project_id = _create(
        http,
        title=fields.pop("title", "Shop"),
        summary="An online shop",
        role="Backend",
        contribution="The API",
        technologies=["Python"],
        **fields,
    )
    assert http.post(f"{PROJECTS}/{project_id}/publish").status_code == 200
    return project_id


def _repository_id(db: Session, repo_id: int):
    return db.scalar(select(GitHubRepository.id).where(GitHubRepository.github_repo_id == repo_id))


def _synced(db: Session, repo_id: int, languages: dict | None = None, at=OLD) -> None:
    """Both categories have succeeded, as a finished sync leaves them."""
    repository_id = _repository_id(db, repo_id)
    db.execute(
        update(GitHubRepository)
        .where(GitHubRepository.id == repository_id)
        .values(languages={"Python": 100} if languages is None else languages)
    )
    github_service.record_category_success(db, repository_id, "metadata", at)
    github_service.record_category_success(db, repository_id, "languages", at)
    db.expire_all()


def _linked(env: Env, db: Session, repo_id: int = 1, synced: bool = True, **repo_fields) -> str:
    """A published project linked to a repository of the user, synced by default."""
    env.github.add(_repo(repo_id, **repo_fields))
    project_id = _published(env.http, title=f"Project {repo_fields.get('name', repo_id)}")
    resp = _link(env.http, project_id, f"{LOGIN}/{repo_fields.get('name', f'repo-{repo_id}')}")
    assert resp.status_code == 200, resp.text
    if synced:
        _synced(db, repo_id)
    return project_id


def _set_unavailable(db: Session, repo_id: int, value) -> None:
    db.execute(
        update(GitHubRepository)
        .where(GitHubRepository.github_repo_id == repo_id)
        .values(unavailable_since=value)
    )
    db.expire_all()


def _set_relation(db: Session, project_id: str, relation: str) -> None:
    db.execute(
        update(ProjectRepository)
        .where(ProjectRepository.project_id == project_id)
        .values(relation=relation)
    )
    db.expire_all()


def _set_job_status(db: Session, repo_id: int, status: str) -> None:
    db.execute(
        update(GitHubSyncJob)
        .where(GitHubSyncJob.github_repository_id == _repository_id(db, repo_id))
        .values(status=status)
    )
    db.expire_all()


def _delete_category(db: Session, repo_id: int, category: str) -> None:
    db.execute(
        delete(GitHubSyncCategoryStatus).where(
            GitHubSyncCategoryStatus.github_repository_id == _repository_id(db, repo_id),
            GitHubSyncCategoryStatus.category == category,
        )
    )
    db.expire_all()


class TestWhitelist:
    def test_exact_keys(self, env, visitor, db_session):
        project_id = _linked(env, db_session)

        assert set(_card_github(visitor, env.http, project_id)) == PUBLIC_GITHUB_KEYS

    def test_nothing_internal_in_the_response(self, env, visitor, db_session):
        project_id = _linked(
            env, db_session, 987654321, name="shop", description="Stored description"
        )
        repository_id = _repository_id(db_session, 987654321)
        job_id = db_session.scalar(
            select(GitHubSyncJob.id).where(GitHubSyncJob.github_repository_id == repository_id)
        )
        github_service.record_category_error(
            db_session, repository_id, "languages", "GITHUB_UNAVAILABLE", T0
        )
        db_session.expire_all()

        resp = visitor.get(f"{PUBLIC}/{_slug(env.http)}")

        card = resp.json()["other"][0]
        assert card["github"]["description"] == "Stored description"
        assert card["id"] == project_id
        # The avatar URL of the profile has the user's GitHub id, so only the block is read.
        assert str(GITHUB_ID) not in json.dumps(card["github"])
        for leaked in [
            "987654321",
            str(repository_id),
            str(job_id),
            "github_repo_id",
            "owner_github_id",
            "owner_login",
            '"unavailable',
            '"sync"',
            "last_success_at",
            "next_manual_sync_at",
            "relation_checked_at",
            "last_error",
            "GITHUB_UNAVAILABLE",
            "QUEUED",
            "etag",
            "stargazers",
            "forks_count",
        ]:
            assert leaked not in resp.text, leaked

    def test_the_schema_has_no_lost_relation(self):
        fields = {
            "full_name": "a/b",
            "html_url": "https://github.com/a/b",
            "description": None,
            "languages": [],
            "pushed_at": None,
            "is_fork": False,
            "parent_full_name": None,
            "is_archived": False,
            "synced_at": T0,
        }
        assert PublicGitHub(**fields, relation="OWNER").relation == "OWNER"
        with pytest.raises(ValidationError):
            PublicGitHub(**fields, relation="NONE")

    def test_the_schema_requires_a_date(self):
        with pytest.raises(ValidationError):
            PublicGitHub(
                full_name="a/b",
                html_url="https://github.com/a/b",
                description=None,
                languages=[],
                pushed_at=None,
                is_fork=False,
                parent_full_name=None,
                is_archived=False,
                relation="OWNER",
                synced_at=None,
            )


class TestFields:
    def test_values_of_a_repository(self, env, visitor, db_session):
        project_id = _linked(env, db_session, description="A shop")

        assert _card_github(visitor, env.http, project_id) == {
            "full_name": f"{LOGIN}/repo-1",
            "html_url": f"https://github.com/{LOGIN}/repo-1",
            "description": "A shop",
            "languages": [{"name": "Python", "bytes": 100}],
            "pushed_at": "2026-10-01T10:00:00Z",
            "is_fork": False,
            "parent_full_name": None,
            "is_archived": False,
            "relation": "OWNER",
            "synced_at": "2026-09-30T12:00:00Z",
        }

    def test_languages_by_bytes_then_name(self, env, visitor, db_session):
        project_id = _linked(env, db_session)
        _synced(db_session, 1, {"Go": 100, "Python": 300, "C": 100})

        languages = _card_github(visitor, env.http, project_id)["languages"]

        assert languages == [
            {"name": "Python", "bytes": 300},
            {"name": "C", "bytes": 100},
            {"name": "Go", "bytes": 100},
        ]

    def test_no_languages_is_an_empty_list(self, env, visitor, db_session):
        project_id = _linked(env, db_session)
        _synced(db_session, 1, {})

        assert _card_github(visitor, env.http, project_id)["languages"] == []

    def test_null_description_and_push_date(self, env, visitor, db_session):
        project_id = _linked(env, db_session, pushed_at=None)

        github = _card_github(visitor, env.http, project_id)

        assert (github["description"], github["pushed_at"]) == (None, None)

    def test_a_fork_with_its_parent(self, env, visitor, db_session):
        parent = {"full_name": "octocat/original"}
        project_id = _linked(env, db_session, fork=True, parent=parent)

        github = _card_github(visitor, env.http, project_id)

        assert (github["is_fork"], github["parent_full_name"]) == (True, "octocat/original")

    def test_an_archived_repository(self, env, visitor, db_session):
        project_id = _linked(env, db_session, archived=True)

        assert _card_github(visitor, env.http, project_id)["is_archived"] is True

    def test_a_contributor(self, env, visitor, db_session):
        env.github.add(_repo(1, STRANGER, STRANGER_ID), contributors=[[GITHUB_ID]])
        project_id = _published(env.http)
        assert _link(env.http, project_id, f"{STRANGER}/repo-1").status_code == 200
        _synced(db_session, 1)

        github = _card_github(visitor, env.http, project_id)

        assert (github["relation"], github["full_name"]) == ("CONTRIBUTOR", f"{STRANGER}/repo-1")


class TestNull:
    def test_no_link(self, env, visitor):
        project_id = _published(env.http)

        assert _card_github(visitor, env.http, project_id) is None

    def test_unlinked(self, env, visitor, db_session):
        project_id = _linked(env, db_session)
        assert env.http.delete(f"{PROJECTS}/{project_id}/repository").status_code == 200

        assert _card_github(visitor, env.http, project_id) is None

    def test_no_sync_at_all(self, env, visitor, db_session):
        project_id = _linked(env, db_session, synced=False)
        _delete_category(db_session, 1, "metadata")

        assert _card_github(visitor, env.http, project_id) is None

    def test_only_metadata_after_a_link(self, env, visitor, db_session):
        project_id = _linked(env, db_session, synced=False)

        assert _card_github(visitor, env.http, project_id) is None

    def test_only_languages(self, env, visitor, db_session):
        project_id = _linked(env, db_session)
        _delete_category(db_session, 1, "metadata")

        assert _card_github(visitor, env.http, project_id) is None

    @pytest.mark.parametrize("failed", ["languages", "metadata"])
    def test_a_category_with_only_an_error(self, env, visitor, db_session, failed):
        project_id = _linked(env, db_session)
        _delete_category(db_session, 1, failed)
        repository_id = _repository_id(db_session, 1)
        github_service.record_category_error(
            db_session, repository_id, failed, "GITHUB_UNAVAILABLE", T0
        )
        db_session.expire_all()

        assert _card_github(visitor, env.http, project_id) is None

    def test_an_unavailable_repository(self, env, visitor, db_session):
        project_id = _linked(env, db_session)
        _set_unavailable(db_session, 1, T0)

        assert _card_github(visitor, env.http, project_id) is None

    def test_a_lost_relation(self, env, visitor, db_session):
        project_id = _linked(env, db_session)
        _set_relation(db_session, project_id, "NONE")

        assert _card_github(visitor, env.http, project_id) is None

    def test_the_card_stays(self, env, visitor, db_session):
        project_id = _linked(env, db_session)
        _set_unavailable(db_session, 1, T0)

        card = _cards(visitor, env.http)[project_id]

        assert (card["title"], card["github"]) == ("Project 1", None)


class TestOldData:
    @pytest.mark.parametrize("status", ["FAILED", "QUEUED", "SYNCING", "SYNCED"])
    def test_the_job_status_does_not_matter(self, env, visitor, db_session, status):
        project_id = _linked(env, db_session)
        _set_job_status(db_session, 1, status)

        github = _card_github(visitor, env.http, project_id)

        assert github["synced_at"] == "2026-09-30T12:00:00Z"
        assert github["languages"] == [{"name": "Python", "bytes": 100}]

    def test_a_later_error_keeps_the_data_and_its_date(self, env, visitor, db_session):
        project_id = _linked(env, db_session)
        repository_id = _repository_id(db_session, 1)
        for category in ("metadata", "languages"):
            github_service.record_category_error(
                db_session, repository_id, category, "GITHUB_UNAVAILABLE", T0
            )
        db_session.expire_all()

        github = _card_github(visitor, env.http, project_id)

        assert github["synced_at"] == "2026-09-30T12:00:00Z"

    @pytest.mark.parametrize(
        ("metadata", "languages"), [(OLD, OLDER), (OLDER, OLD)], ids=["languages", "metadata"]
    )
    def test_the_date_is_of_the_oldest_category(
        self, env, visitor, db_session, metadata, languages
    ):
        project_id = _linked(env, db_session)
        repository_id = _repository_id(db_session, 1)
        github_service.record_category_success(db_session, repository_id, "metadata", metadata)
        github_service.record_category_success(db_session, repository_id, "languages", languages)
        db_session.expire_all()

        github = _card_github(visitor, env.http, project_id)

        assert github["synced_at"] == "2026-08-31T12:00:00Z"

    def test_no_age_hides_the_data(self, env, visitor, db_session):
        project_id = _linked(env, db_session)
        _synced(db_session, 1, at=T0 - timedelta(days=3650))

        assert _card_github(visitor, env.http, project_id) is not None


class TestSameDateAsTheCabinet:
    def _both(self, env, visitor, project_id: str) -> tuple:
        cabinet = env.http.get(f"{PROJECTS}/{project_id}").json()["github"]["synced_at"]
        public = _card_github(visitor, env.http, project_id)
        return cabinet, public and public["synced_at"]

    def test_after_a_link(self, env, visitor, db_session):
        project_id = _linked(env, db_session, synced=False)

        assert self._both(env, visitor, project_id) == (None, None)

    def test_after_a_sync(self, env, visitor, db_session):
        project_id = _linked(env, db_session)

        cabinet, public = self._both(env, visitor, project_id)

        assert cabinet == public == "2026-09-30T12:00:00Z"

    @pytest.mark.parametrize(
        ("metadata", "languages"), [(OLD, OLDER), (OLDER, OLD)], ids=["languages", "metadata"]
    )
    def test_with_categories_of_different_age(self, env, visitor, db_session, metadata, languages):
        project_id = _linked(env, db_session)
        repository_id = _repository_id(db_session, 1)
        github_service.record_category_success(db_session, repository_id, "metadata", metadata)
        github_service.record_category_success(db_session, repository_id, "languages", languages)
        db_session.expire_all()

        cabinet, public = self._both(env, visitor, project_id)

        assert cabinet == public == "2026-08-31T12:00:00Z"

    def test_with_a_category_with_only_an_error(self, env, visitor, db_session):
        project_id = _linked(env, db_session, synced=False)
        github_service.record_category_error(
            db_session, _repository_id(db_session, 1), "languages", "GITHUB_UNAVAILABLE", T0
        )
        db_session.expire_all()

        assert self._both(env, visitor, project_id) == (None, None)


class TestRecovery:
    def test_a_repository_that_came_back(self, env, visitor, db_session):
        project_id = _linked(env, db_session)
        _set_unavailable(db_session, 1, T0)
        assert _card_github(visitor, env.http, project_id) is None

        _set_unavailable(db_session, 1, None)

        assert _card_github(visitor, env.http, project_id) is not None

    def test_a_relation_that_came_back(self, env, visitor, db_session):
        project_id = _linked(env, db_session)
        _set_relation(db_session, project_id, "NONE")
        assert _card_github(visitor, env.http, project_id) is None

        _set_relation(db_session, project_id, "CONTRIBUTOR")

        assert _card_github(visitor, env.http, project_id)["relation"] == "CONTRIBUTOR"


class TestSharedRepository:
    @pytest.fixture
    def shared(self, env, make_auth_client, db_session):
        """Two users link one repository from their published profiles."""
        env.github.add(_repo(1), contributors=[[OTHER_GITHUB_ID]])
        mine = _published(env.http)
        assert _link(env.http, mine, f"{LOGIN}/repo-1").status_code == 200
        other, _ = _other_user(make_auth_client, db_session)
        _publish_profile(other)
        theirs = _published(other)
        assert _link(other, theirs, f"{LOGIN}/repo-1").status_code == 200
        _synced(db_session, 1)
        return mine, other, theirs

    def test_each_has_its_own_relation(self, env, visitor, shared):
        mine, other, theirs = shared

        assert _card_github(visitor, env.http, mine)["relation"] == "OWNER"
        assert _card_github(visitor, other, theirs)["relation"] == "CONTRIBUTOR"

    def test_a_lost_relation_hides_only_that_link(self, env, visitor, db_session, shared):
        mine, other, theirs = shared
        _set_relation(db_session, theirs, "NONE")

        assert _card_github(visitor, other, theirs) is None
        assert _card_github(visitor, env.http, mine)["relation"] == "OWNER"

    def test_an_unavailable_repository_hides_both(self, env, visitor, db_session, shared):
        mine, other, theirs = shared
        _set_unavailable(db_session, 1, T0)

        assert _card_github(visitor, env.http, mine) is None
        assert _card_github(visitor, other, theirs) is None


class TestVisibility:
    def test_a_draft_is_not_shown(self, env, visitor, db_session):
        env.github.add(_repo(1))
        project_id = _create(env.http, title="Draft")
        assert _link(env.http, project_id, f"{LOGIN}/repo-1").status_code == 200
        _synced(db_session, 1)

        resp = visitor.get(f"{PUBLIC}/{_slug(env.http)}")

        assert "repo-1" not in resp.text
        assert project_id not in resp.text

    def test_a_hidden_project_is_not_shown(self, env, visitor, db_session):
        project_id = _linked(env, db_session)
        resp = env.http.post(f"{PROJECTS}/{project_id}/visibility", json={"visibility": "PRIVATE"})
        assert resp.status_code == 200, resp.text

        resp = visitor.get(f"{PUBLIC}/{_slug(env.http)}")

        assert "repo-1" not in resp.text
        assert project_id not in resp.text

    def test_an_archived_project_is_not_shown(self, env, visitor, db_session):
        project_id = _linked(env, db_session)
        assert env.http.post(f"{PROJECTS}/{project_id}/archive").status_code == 200

        resp = visitor.get(f"{PUBLIC}/{_slug(env.http)}")

        assert "repo-1" not in resp.text
        assert project_id not in resp.text

    def test_a_private_profile_is_404(self, env, visitor, db_session):
        _linked(env, db_session)
        slug = _slug(env.http)
        assert env.http.post("/api/v1/profile/unpublish").status_code == 200

        resp = visitor.get(f"{PUBLIC}/{slug}")

        assert resp.status_code == 404
        assert "repo-1" not in resp.text


class TestCards:
    def test_featured_and_other_carry_their_own_repository(self, env, visitor, db_session):
        featured = _linked(env, db_session, 1)
        other = _linked(env, db_session, 2)
        plain = _published(env.http, title="Plain")
        assert env.http.post(f"{PROJECTS}/{featured}/showcase").status_code == 200

        body = _body(visitor, env.http)

        assert [card["id"] for card in body["featured"]] == [featured]
        assert body["featured"][0]["github"]["full_name"] == f"{LOGIN}/repo-1"
        others = {card["id"]: card["github"] for card in body["other"]}
        assert others[other]["full_name"] == f"{LOGIN}/repo-2"
        assert others[plain] is None

    def test_a_profile_without_projects(self, env, visitor):
        body = _body(visitor, env.http)

        assert (body["featured"], body["other"]) == ([], [])


class TestNoGitHubAndNoWrites:
    def test_no_request_and_no_budget(self, env, visitor, db_session, monkeypatch):
        _linked(env, db_session)
        slug = _slug(env.http)
        requests = len(env.github.requests)

        def fail(*args, **kwargs):
            raise AssertionError("a public read must not reach GitHub or the budget")

        monkeypatch.setattr(GitHubApiClient, "_get", fail)
        monkeypatch.setattr(UserRequestBudget, "spend", fail)

        resp = visitor.get(f"{PUBLIC}/{slug}")

        assert resp.status_code == 200, resp.text
        assert resp.json()["other"][0]["github"] is not None
        assert len(env.github.requests) == requests

    def test_only_selects_and_no_new_job(self, env, visitor, db_session):
        _linked(env, db_session)
        # An unsynced repository queues nothing either.
        _linked(env, db_session, 2, synced=False)
        slug = _slug(env.http)
        jobs = db_session.scalar(select(func.count()).select_from(GitHubSyncJob))
        statements: list[str] = []

        def record(conn, cursor, statement, *args) -> None:
            statements.append(statement)

        connection = db_session.connection()
        event.listen(connection, "before_cursor_execute", record)
        try:
            resp = visitor.get(f"{PUBLIC}/{slug}")
        finally:
            event.remove(connection, "before_cursor_execute", record)

        assert resp.status_code == 200, resp.text
        # Profile, contacts, projects, technologies, GitHub data.
        assert len(statements) == 5
        assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
        assert db_session.scalar(select(func.count()).select_from(GitHubSyncJob)) == jobs


class TestQueryCount:
    def _statements(self, env: Env, visitor, db_session: Session, slug: str) -> int:
        seen: list[str] = []

        def count(conn, cursor, statement, *args) -> None:
            seen.append(statement)

        connection = db_session.connection()
        event.listen(connection, "before_cursor_execute", count)
        try:
            resp = visitor.get(f"{PUBLIC}/{slug}")
        finally:
            event.remove(connection, "before_cursor_execute", count)
        assert resp.status_code == 200, resp.text
        return len(seen)

    def test_same_number_of_queries_for_1_and_30_projects(self, env, visitor, db_session):
        # 30 links read GitHub 30 times; the default budget of 60 would be the limit.
        env.budget = UserRequestBudget(1000)
        slug = _slug(env.http)
        first = _linked(env, db_session, 1)
        one = self._statements(env, visitor, db_session, slug)

        projects = [first] + [_linked(env, db_session, repo_id) for repo_id in range(2, 31)]
        cards = _cards(visitor, env.http)
        assert len(cards) == 30 and all(card["github"] for card in cards.values())
        thirty_linked = self._statements(env, visitor, db_session, slug)

        for project_id in projects[::2]:
            assert env.http.delete(f"{PROJECTS}/{project_id}/repository").status_code == 200
        cards = _cards(visitor, env.http)
        assert sum(card["github"] is None for card in cards.values()) == 15
        thirty_mixed = self._statements(env, visitor, db_session, slug)

        # Profile, contacts, projects, technologies, GitHub data.
        assert one == thirty_linked == thirty_mixed == 5
