"""POST /integrations/github/repositories/{id}/import (ADR-017, step 5.5): a DRAFT +
PRIVATE project titled after the repository and its link, in one transaction; the
relation check, the project limit, errors, budget, races and transactions."""

import threading
import uuid
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.errors import AppError
from app.github import service as github_service
from app.github.client import GitHubRepositoryData
from app.models.github import ProjectRepository
from app.models.identity import Profile, User
from app.models.projects import Project
from app.projects import service as project_service
from tests.conftest import wait_until_blocked
from tests.test_github_link_api import (
    BODY_MARKER,
    GITHUB_ID,
    GITHUB_KEYS,
    LOGIN,
    OTHER_GITHUB_ID,
    PROJECTS,
    STRANGER,
    STRANGER_ID,
    T0,
    Env,
    _error,
    _links,
    _new_client,
    _other_user,
    _repo,
    _repository_rows,
    _timeout,
    make_env,
)

REPOSITORIES = "/api/v1/integrations/github/repositories"
PROJECT_KEYS = {
    "id",
    "status",
    "visibility",
    "title",
    "summary",
    "description",
    "problem",
    "results",
    "role",
    "contribution",
    "technologies",
    "featured_position",
    "github",
}


@pytest.fixture
def env(make_auth_client, db_session: Session) -> Env:
    return make_env(make_auth_client, db_session)


def _import(http: TestClient, repository_id: int | str) -> httpx.Response:
    return http.post(f"{REPOSITORIES}/{repository_id}/import")


def _projects(db: Session, owner_id: uuid.UUID) -> list[Project]:
    return list(db.scalars(select(Project).where(Project.owner_id == owner_id)))


def _assert_nothing_stored(env: Env, db: Session, github_repo_id: int) -> None:
    assert _projects(db, env.user.id) == []
    assert _links(db) == []
    assert _repository_rows(db, github_repo_id) == []


def _seed_projects(db: Session, owner_id: uuid.UUID, count: int) -> None:
    # Committed, as the application's own data is: the route ends its read
    # transaction before calling GitHub.
    db.add_all([Project(owner_id=owner_id) for _ in range(count)])
    db.commit()


# The project and its link.


def test_own_repository_is_imported_as_a_draft_private_project(env, db_session):
    env.github.add(_repo(1, description="Payments API"))

    resp = _import(env.http, 1)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == PROJECT_KEYS
    project_id = body["id"]
    # The title is the repository's name; GitHub's description stays GitHub data.
    assert {key: value for key, value in body.items() if key not in {"id", "github"}} == {
        "status": "DRAFT",
        "visibility": "PRIVATE",
        "title": "repo-1",
        "summary": None,
        "description": None,
        "problem": None,
        "results": None,
        "role": None,
        "contribution": None,
        "technologies": [],
        "featured_position": None,
    }
    assert set(body["github"]) == GITHUB_KEYS
    assert body["github"] == {
        "github_repo_id": 1,
        "full_name": f"{LOGIN}/repo-1",
        "html_url": f"https://github.com/{LOGIN}/repo-1",
        "description": "Payments API",
        "languages": [],
        "pushed_at": "2026-10-01T10:00:00Z",
        "is_fork": False,
        "parent_full_name": None,
        "is_archived": False,
        "relation": "OWNER",
        "unavailable": False,
        "synced_at": None,
        "sync": {"status": "NOT_SYNCED", "last_success_at": None, "next_manual_sync_at": None},
    }
    # Read by id: no redirect, one request for an owned repository.
    assert [r.url.path for r in env.github.requests] == ["/repositories/1"]
    assert env.budget.spent(env.user.id, T0) == 1
    assert _links(db_session) == [(uuid.UUID(project_id), env.user.id, 1, "OWNER", T0)]
    assert _repository_rows(db_session, 1) == [(f"{LOGIN}/repo-1", "Payments API", None, None)]


def test_imported_project_is_in_the_cabinet_and_not_on_the_public_profile(env, make_auth_client):
    env.github.add(_repo(1))
    env.http.patch("/api/v1/profile", json={"display_name": "Ann", "headline": "Dev"})
    assert env.http.post("/api/v1/profile/publish").status_code == 200
    slug = env.http.get("/api/v1/profile").json()["slug"]

    body = _import(env.http, 1).json()

    assert env.http.get(f"{PROJECTS}/{body['id']}").json() == body
    items = env.http.get(PROJECTS).json()["items"]
    assert [(item["id"], item["status"], item["title"]) for item in items] == [
        (body["id"], "DRAFT", "repo-1")
    ]
    visitor = _new_client(make_auth_client, send_origin=False)
    public = visitor.get(f"/api/v1/public/profiles/{slug}")
    assert public.status_code == 200, public.text
    assert public.json()["featured"] == []
    assert public.json()["other"] == []


def test_contributor_is_found_by_numeric_id_across_pages(env, db_session):
    env.github.add(_repo(2, owner=STRANGER, owner_id=STRANGER_ID), contributors=[[7], [GITHUB_ID]])

    resp = _import(env.http, 2)

    assert resp.status_code == 201, resp.text
    assert resp.json()["github"]["relation"] == "CONTRIBUTOR"
    assert [r.url.path for r in env.github.requests] == [
        "/repositories/2",
        f"/repos/{STRANGER}/repo-2/contributors",
        f"/repos/{STRANGER}/repo-2/contributors",
    ]
    assert env.budget.spent(env.user.id, T0) == 3
    assert _links(db_session)[0][2:4] == (2, "CONTRIBUTOR")


@pytest.mark.parametrize(
    "contributors",
    [
        [[7, 8]],
        None,  # 204: no contributors
        [[GITHUB_ID + 1]],  # another id, as a renamed login could have
        [[7]] * 5 + [[GITHUB_ID]],  # beyond the five pages read
    ],
    ids=["absent", "no-contributors", "other-id", "beyond-five-pages"],
)
def test_neither_owner_nor_contributor_is_refused(env, db_session, contributors):
    env.github.add(_repo(3, owner=STRANGER, owner_id=STRANGER_ID), contributors=contributors)

    resp = _import(env.http, 3)

    error = _error(resp, 422, "GITHUB_RELATION_NOT_FOUND")
    assert "contributor list" in error["message"]
    assert len(env.github.requests) <= 6
    _assert_nothing_stored(env, db_session, 3)


@pytest.mark.parametrize("name", ["a" * 100, "x", "my.repo_name-2", "...", "-_.", "Repo.With.Dots"])
def test_title_is_the_repository_name_as_is(env, db_session, name):
    env.github.add(_repo(4, name=name))

    resp = _import(env.http, 4)

    assert resp.status_code == 201, resp.text
    assert resp.json()["title"] == name
    assert _projects(db_session, env.user.id)[0].title == name


@pytest.mark.parametrize(
    "name",
    ["a" * 101, " spaced ", "two words", ".", "..", "имя", "tab\tname"],
    ids=["101-chars", "edge-spaces", "inner-space", "dot", "dot-dot", "non-ascii", "control"],
)
def test_name_github_would_not_allow_is_a_malformed_answer(env, db_session, name):
    env.github.add(_repo(5, name=name))

    resp = _import(env.http, 5)

    _error(resp, 502, "GITHUB_UNAVAILABLE")
    _assert_nothing_stored(env, db_session, 5)


def test_fork_and_archived_repository_keep_their_flags(env):
    env.github.add(
        _repo(6, fork=True, archived=True, parent={"full_name": "upstream/repo-6"}),
    )

    github = _import(env.http, 6).json()["github"]

    assert (github["is_fork"], github["is_archived"], github["parent_full_name"]) == (
        True,
        True,
        "upstream/repo-6",
    )


def test_github_is_called_outside_any_transaction(env):
    env.github.add(_repo(2, owner=STRANGER, owner_id=STRANGER_ID), contributors=[[GITHUB_ID]])

    assert _import(env.http, 2).status_code == 201

    assert env.in_transaction == [False, False]


# Conflicts and the project limit.


def test_importing_the_same_repository_again_is_a_conflict(env, db_session):
    env.github.add(_repo(1))
    first = _import(env.http, 1).json()["id"]
    env.github.requests.clear()

    error = _error(_import(env.http, 1), 409, "GITHUB_REPOSITORY_ALREADY_LINKED")

    assert error["details"] == {"project_id": first}
    # Known before GitHub is called: the user's budget is spared.
    assert env.github.requests == []
    assert [project.id for project in _projects(db_session, env.user.id)] == [uuid.UUID(first)]
    assert len(_links(db_session)) == 1


def test_repository_linked_to_an_existing_project_is_a_conflict(env, db_session):
    env.github.add(_repo(1))
    project_id = env.http.post(PROJECTS, json={"title": "Mine"}).json()["id"]
    linked = env.http.post(
        f"{PROJECTS}/{project_id}/repository", json={"full_name": f"{LOGIN}/repo-1"}
    )
    assert linked.status_code == 200, linked.text

    error = _error(_import(env.http, 1), 409, "GITHUB_REPOSITORY_ALREADY_LINKED")

    assert error["details"] == {"project_id": project_id}
    assert len(_projects(db_session, env.user.id)) == 1


def test_link_written_while_github_answered_is_a_conflict(env, db_session):
    """The early check passed; the database's constraint decides in the write
    transaction, and the new project is not kept."""
    env.github.add(_repo(1))
    project_id = env.http.post(PROJECTS, json={"title": "Mine"}).json()["id"]

    def link_meanwhile(request: httpx.Request) -> None:
        if not _links(db_session):
            project = db_session.get(Project, uuid.UUID(project_id))
            checked = github_service.CheckedRepository(
                GitHubRepositoryData(
                    github_repo_id=1,
                    owner_github_id=GITHUB_ID,
                    owner_login=LOGIN,
                    name="repo-1",
                    full_name=f"{LOGIN}/repo-1",
                    html_url=f"https://github.com/{LOGIN}/repo-1",
                    description=None,
                    is_fork=False,
                    is_archived=False,
                    pushed_at=None,
                    parent_full_name=None,
                ),
                "OWNER",
            )
            github_service.store_link(db_session, project, checked, T0)
            db_session.commit()
        return None

    env.github.respond = link_meanwhile

    error = _error(_import(env.http, 1), 409, "GITHUB_REPOSITORY_ALREADY_LINKED")

    assert error["details"] == {"project_id": project_id}
    assert [project.id for project in _projects(db_session, env.user.id)] == [uuid.UUID(project_id)]
    assert len(_links(db_session)) == 1


def test_two_users_import_one_repository(env, make_auth_client, db_session):
    env.github.add(_repo(1), contributors=[[OTHER_GITHUB_ID]])
    other, other_user = _other_user(make_auth_client, db_session)

    mine = _import(env.http, 1)
    theirs = _import(other, 1)

    assert (mine.status_code, theirs.status_code) == (201, 201)
    assert mine.json()["github"]["relation"] == "OWNER"
    assert theirs.json()["github"]["relation"] == "CONTRIBUTOR"
    assert len(_repository_rows(db_session, 1)) == 1
    assert sorted((owner, relation) for _, owner, _, relation, _ in _links(db_session)) == sorted(
        [(env.user.id, "OWNER"), (other_user.id, "CONTRIBUTOR")]
    )


def test_project_limit_is_checked_before_github(env, db_session):
    env.github.add(_repo(1))
    _seed_projects(db_session, env.user.id, 50)

    error = _error(_import(env.http, 1), 409, "PROJECT_LIMIT_REACHED")

    assert error["details"] == {"limit": 50}
    assert env.github.requests == []
    assert env.budget.spent(env.user.id, T0) == 0
    assert len(_projects(db_session, env.user.id)) == 50
    assert _links(db_session) == []


def test_fiftieth_project_can_be_imported(env, db_session):
    env.github.add(_repo(1))
    _seed_projects(db_session, env.user.id, 49)

    assert _import(env.http, 1).status_code == 201

    assert len(_projects(db_session, env.user.id)) == 50
    _error(env.http.post(PROJECTS, json={}), 409, "PROJECT_LIMIT_REACHED")


def test_limit_reached_while_github_answered_stores_nothing(env, db_session):
    env.github.add(_repo(1))
    _seed_projects(db_session, env.user.id, 49)

    def fiftieth_meanwhile(request: httpx.Request) -> None:
        if len(_projects(db_session, env.user.id)) == 49:
            _seed_projects(db_session, env.user.id, 1)
        return None

    env.github.respond = fiftieth_meanwhile

    _error(_import(env.http, 1), 409, "PROJECT_LIMIT_REACHED")

    assert len(_projects(db_session, env.user.id)) == 50
    assert _links(db_session) == []
    assert _repository_rows(db_session, 1) == []


# Atomicity: the project and the link are stored together or not at all.


class _WriteFailed(Exception):
    pass


def test_failed_link_write_leaves_no_project(env, db_session, monkeypatch):
    env.github.add(_repo(1))
    store_link = github_service.store_link

    def failing(*args, **kwargs):
        store_link(*args, **kwargs)
        raise _WriteFailed

    monkeypatch.setattr(github_service, "store_link", failing)

    _error(_import(env.http, 1), 500, "INTERNAL_ERROR")

    _assert_nothing_stored(env, db_session, 1)


def test_failed_project_write_leaves_no_link(env, db_session, monkeypatch):
    env.github.add(_repo(1))
    create_project = project_service.create_project

    def failing(*args, **kwargs):
        create_project(*args, **kwargs)
        raise _WriteFailed

    monkeypatch.setattr(project_service, "create_project", failing)

    _error(_import(env.http, 1), 500, "INTERNAL_ERROR")

    _assert_nothing_stored(env, db_session, 1)


# Path, session and Origin.


@pytest.mark.parametrize(
    "repository_id",
    ["0", "-1", "+1", "01", "1.5", "1e3", "abc", "%201", "１", "9223372036854775808", "9" * 30],
)
def test_malformed_id_is_not_found_before_github(env, repository_id):
    error = _error(_import(env.http, repository_id), 404, "NOT_FOUND")

    assert error["details"] == {}
    assert env.github.requests == []
    assert env.budget.spent(env.user.id, T0) == 0


def test_largest_id_is_read_from_github(env, db_session):
    resp = _import(env.http, "9223372036854775807")

    _error(resp, 404, "NOT_FOUND")
    assert [r.url.path for r in env.github.requests] == ["/repositories/9223372036854775807"]


def test_requires_a_session(env, make_auth_client):
    anonymous = _new_client(make_auth_client)

    _error(_import(anonymous, 1), 401, "UNAUTHORIZED")
    assert env.github.requests == []


def test_needs_the_frontend_origin(env, make_auth_client, db_session):
    env.github.add(_repo(1))
    no_origin = _new_client(make_auth_client, send_origin=False)
    no_origin.cookies = env.http.cookies

    _error(_import(no_origin, 1), 403, "CSRF_ORIGIN_INVALID")
    assert env.github.requests == []
    _assert_nothing_stored(env, db_session, 1)


# Budget, pause and GitHub errors: nothing is stored.


def test_exhausted_user_budget_is_refused_before_github(env, db_session):
    env.github.add(_repo(1))
    # 5 left: an import reserves 6, its worst case (ADR-018).
    env.budget.charge(env.user.id, 55, T0 - timedelta(minutes=45))

    resp = _import(env.http, 1)

    error = _error(resp, 429, "GITHUB_USER_LIMIT_REACHED")
    assert error["details"] == {"retry_after_seconds": 900}
    assert resp.headers["Retry-After"] == "900"
    assert env.github.requests == []
    _assert_nothing_stored(env, db_session, 1)


def test_six_requests_left_are_enough_for_an_import(env):
    env.github.add(_repo(1))
    env.budget.charge(env.user.id, 54, T0 - timedelta(minutes=45))

    assert _import(env.http, 1).status_code == 201


def test_platform_pause_is_503_without_calling_github(env, db_session):
    env.github.add(_repo(1))
    env.pause.start(T0 + timedelta(seconds=45))

    resp = _import(env.http, 1)

    assert _error(resp, 503, "GITHUB_RATE_LIMITED")["details"] == {"retry_after_seconds": 45}
    assert resp.headers["Retry-After"] == "45"
    assert env.github.requests == []
    assert env.budget.spent(env.user.id, T0) == 0
    _assert_nothing_stored(env, db_session, 1)


@pytest.mark.parametrize("repo", [_repo(1, private=True), None], ids=["private", "404"])
def test_missing_or_private_repository_is_not_found(env, db_session, repo):
    if repo is not None:
        env.github.add(repo)

    resp = _import(env.http, 1)

    # The repository is the resource named in the path (ADR-017).
    assert _error(resp, 404, "NOT_FOUND")["details"] == {}
    assert env.budget.spent(env.user.id, T0) == 1
    _assert_nothing_stored(env, db_session, 1)


@pytest.mark.parametrize(
    "respond",
    [
        lambda r: httpx.Response(502, text=BODY_MARKER),
        _timeout,
        lambda r: httpx.Response(200, text=BODY_MARKER),
        # The repository reads, its contributor list fails.
        lambda r: httpx.Response(500, text=BODY_MARKER) if "contributors" in r.url.path else None,
    ],
    ids=["5xx", "timeout", "not-json", "contributors-5xx"],
)
def test_github_failure_is_502_and_stores_nothing(env, db_session, respond):
    env.github.add(_repo(1, owner=STRANGER, owner_id=STRANGER_ID))
    env.github.respond = respond

    resp = _import(env.http, 1)

    assert _error(resp, 502, "GITHUB_UNAVAILABLE")["details"] == {}
    assert BODY_MARKER not in resp.text
    _assert_nothing_stored(env, db_session, 1)


# Races between two real transactions (as in step 5.4).


class TestRaces:
    def _seed(self, db_engine, projects: int) -> uuid.UUID:
        """A user with a profile and `projects` projects."""
        with Session(db_engine) as db:
            suffix = uuid.uuid4().hex[:8]
            user = User(
                github_user_id=900_000 + uuid.uuid4().int % 100_000,
                github_login=f"race-{suffix}",
            )
            db.add(user)
            db.flush()
            db.add(Profile(user_id=user.id, slug=f"race-{suffix}", status="PRIVATE"))
            db.add_all([Project(owner_id=user.id) for _ in range(projects)])
            db.commit()
            return user.id

    def _cleanup(self, db_engine, user_id: uuid.UUID, github_repo_id: int) -> None:
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
            conn.execute(
                text("DELETE FROM github_repositories WHERE github_repo_id = :id"),
                {"id": github_repo_id},
            )

    def _checked(self, github_repo_id: int) -> github_service.CheckedRepository:
        return github_service.CheckedRepository(
            GitHubRepositoryData(
                github_repo_id=github_repo_id,
                owner_github_id=GITHUB_ID,
                owner_login=LOGIN,
                name="race",
                full_name=f"{LOGIN}/race",
                html_url=f"https://github.com/{LOGIN}/race",
                description=None,
                is_fork=False,
                is_archived=False,
                pushed_at=None,
                parent_full_name=None,
            ),
            "OWNER",
        )

    # The route's write transaction.
    def _import(self, db: Session, user_id: uuid.UUID, github_repo_id: int) -> None:
        user = db.get(User, user_id)
        project_service.create_imported_project(db, user, self._checked(github_repo_id), T0)

    # POST /projects's write transaction.
    def _create(self, db: Session, user_id: uuid.UUID) -> None:
        user = db.get(User, user_id)
        project_service.lock_owner_profile(db, user)
        project_service.create_project(db, user, {}, None)

    def _race(self, db_engine, first_step, second_step, first_outcome: str) -> dict:
        result: dict = {}
        with Session(db_engine) as first, Session(db_engine) as second:
            first_step(first)
            pid = second.execute(text("SELECT pg_backend_pid()")).scalar_one()

            def run() -> None:
                try:
                    second_step(second)
                    second.commit()
                    result["ok"] = True
                except Exception as exc:  # reported in the main thread
                    second.rollback()
                    result["error"] = exc

            thread = threading.Thread(target=run)
            thread.start()
            wait_until_blocked(db_engine, pid)
            getattr(first, first_outcome)()
            thread.join(timeout=10)
            assert not thread.is_alive()
        return result

    def _rows(self, db_engine, user_id: uuid.UUID) -> tuple[int, list[uuid.UUID]]:
        with db_engine.connect() as conn:
            projects = conn.execute(
                select(func.count()).select_from(Project).where(Project.owner_id == user_id)
            ).scalar_one()
            linked = conn.execute(
                select(ProjectRepository.project_id).where(ProjectRepository.owner_id == user_id)
            ).scalars()
            return projects, list(linked)

    @pytest.mark.parametrize("first_outcome", ["commit", "rollback"])
    def test_two_imports_of_one_repository_make_one_project(self, db_engine, first_outcome):
        repo_id = 810_000_000 + uuid.uuid4().int % 1_000_000
        user_id = self._seed(db_engine, projects=0)
        try:
            result = self._race(
                db_engine,
                lambda db: self._import(db, user_id, repo_id),
                lambda db: self._import(db, user_id, repo_id),
                first_outcome,
            )
            projects, linked = self._rows(db_engine, user_id)
            assert projects == 1
            assert len(linked) == 1
            if first_outcome == "commit":
                assert isinstance(result.get("error"), AppError), result
                assert result["error"].code == "GITHUB_REPOSITORY_ALREADY_LINKED"
                assert result["error"].details == {"project_id": str(linked[0])}
            else:
                assert result == {"ok": True}
        finally:
            self._cleanup(db_engine, user_id, repo_id)

    @pytest.mark.parametrize("import_first", [True, False], ids=["import-first", "create-first"])
    def test_import_and_creation_do_not_exceed_the_limit(self, db_engine, import_first):
        repo_id = 810_000_000 + uuid.uuid4().int % 1_000_000
        user_id = self._seed(db_engine, projects=49)
        steps = [
            lambda db: self._import(db, user_id, repo_id),
            lambda db: self._create(db, user_id),
        ]
        if not import_first:
            steps.reverse()
        try:
            result = self._race(db_engine, *steps, "commit")

            assert isinstance(result.get("error"), AppError), result
            assert result["error"].code == "PROJECT_LIMIT_REACHED"
            projects, linked = self._rows(db_engine, user_id)
            assert projects == 50
            assert len(linked) == (1 if import_first else 0)
        finally:
            self._cleanup(db_engine, user_id, repo_id)
