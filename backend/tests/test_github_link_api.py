"""POST and DELETE /projects/{id}/repository (ADR-017, step 5.4): the relation check,
the shared repository row, the link, errors, budget, races and transactions."""

import re
import threading
import uuid
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.errors import AppError
from app.github import service as github_service
from app.github.budget import UserRequestBudget
from app.github.client import (
    GitHubApiClient,
    GitHubRepositoryData,
    RateLimitPause,
    RateLimitState,
)
from app.github.dependencies import get_github_api_client, get_now, get_user_request_budget
from app.main import app
from app.models.github import GitHubRepository, ProjectRepository
from app.models.identity import User
from app.models.projects import Project
from app.projects import service as project_service
from tests.conftest import login, make_github_transport, wait_until_blocked

PROJECTS = "/api/v1/projects"
T0 = datetime(2026, 10, 30, 12, 0, 0)
BODY_MARKER = "LINK_RESPONSE_BODY_MARKER"
# make_github_transport's default user, a second user, and a stranger who owns repositories.
LOGIN, GITHUB_ID = "testuser", 10001
OTHER_LOGIN, OTHER_GITHUB_ID = "otheruser", 10002
STRANGER, STRANGER_ID = "octocat", 583231
GITHUB_KEYS = {
    "github_repo_id",
    "full_name",
    "html_url",
    "description",
    "languages",
    "pushed_at",
    "is_fork",
    "parent_full_name",
    "is_archived",
    "relation",
    "unavailable",
    "synced_at",
    "sync",
}


def _repo(
    repo_id: int, owner: str = LOGIN, owner_id: int = GITHUB_ID, name: str | None = None, **fields
) -> dict:
    name = name or f"repo-{repo_id}"
    return {
        "id": repo_id,
        "name": name,
        "full_name": f"{owner}/{name}",
        "owner": {"login": owner, "id": owner_id, "type": "User"},
        "private": False,
        "html_url": f"https://github.com/{owner}/{name}",
        "description": None,
        "fork": False,
        "archived": False,
        "pushed_at": "2026-10-01T10:00:00Z",
        **fields,
    }


class FakeGitHub:
    """Repositories by name and id, renamed names, and contributor pages by full name."""

    def __init__(self) -> None:
        self.by_name: dict[str, dict] = {}
        self.by_id: dict[int, dict] = {}
        self.moved: dict[str, int] = {}
        self.contributors: dict[str, list[list[int]]] = {}
        self.requests: list[httpx.Request] = []
        self.respond = None

    def add(self, repo: dict, contributors: list[list[int]] | None = None) -> dict:
        self.by_name[repo["full_name"]] = repo
        self.by_id[repo["id"]] = repo
        if contributors is not None:
            self.contributors[repo["full_name"]] = contributors
        return repo

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.respond is not None:
            response = self.respond(request)
            if response is not None:
                return response
        path = request.url.path
        if match := re.fullmatch(r"/repos/([^/]+/[^/]+)/contributors", path):
            pages = self.contributors.get(match.group(1))
            if pages is None:
                return httpx.Response(204)
            page = int(request.url.params["page"])
            headers = {}
            if page < len(pages):
                headers["link"] = f'<https://api.github.com/x?page={page + 1}>; rel="next"'
            body = [{"id": user_id, "login": f"user{user_id}"} for user_id in pages[page - 1]]
            return httpx.Response(200, json=body, headers=headers)
        if match := re.fullmatch(r"/repos/([^/]+/[^/]+)", path):
            full_name = match.group(1)
            if full_name in self.moved:
                location = f"https://api.github.com/repositories/{self.moved[full_name]}"
                return httpx.Response(301, headers={"location": location})
            repo = self.by_name.get(full_name)
        elif match := re.fullmatch(r"/repositories/([0-9]+)", path):
            repo = self.by_id.get(int(match.group(1)))
        else:
            repo = None
        if repo is None:
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(200, json=repo)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@dataclass
class Env:
    http: TestClient
    github: FakeGitHub
    clock: Clock
    budget: UserRequestBudget
    pause: RateLimitPause
    user: User
    # Whether the database session had an open transaction at each GitHub request.
    in_transaction: list[bool] = field(default_factory=list)


@pytest.fixture
def env(make_auth_client, db_session: Session) -> Env:
    http = make_auth_client()
    login(http)
    user = db_session.scalar(select(User).where(User.github_user_id == GITHUB_ID))
    github = FakeGitHub()
    state = Env(
        http=http,
        github=github,
        clock=Clock(T0),
        budget=UserRequestBudget(60),
        pause=RateLimitPause(),
        user=user,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        state.in_transaction.append(db_session.in_transaction())
        return github(request)

    def client() -> Generator[GitHubApiClient]:
        with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
            yield GitHubApiClient(
                http_client,
                "client-id",
                "client-secret",
                rate_limits=RateLimitState(),
                pause=state.pause,
                now=state.clock,
            )

    def db() -> Generator[Session]:
        # As get_db does: an error rolls the request's work back.
        try:
            yield db_session
        except Exception:
            db_session.rollback()
            raise

    # make_auth_client clears every override at teardown.
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_github_api_client] = client
    app.dependency_overrides[get_user_request_budget] = lambda: state.budget
    app.dependency_overrides[get_now] = state.clock
    return state


def _new_client(make_auth_client, *args, **kwargs) -> TestClient:
    # make_auth_client sets its own get_db override; keep the rollback-on-error one.
    db = app.dependency_overrides[get_db]
    http = make_auth_client(*args, **kwargs)
    app.dependency_overrides[get_db] = db
    return http


def _other_user(make_auth_client, db_session: Session) -> tuple[TestClient, User]:
    http = _new_client(
        make_auth_client,
        make_github_transport(github_user_id=OTHER_GITHUB_ID, github_login=OTHER_LOGIN),
    )
    login(http)
    user = db_session.scalar(select(User).where(User.github_user_id == OTHER_GITHUB_ID))
    return http, user


def _create(http: TestClient, **fields) -> str:
    resp = http.post(PROJECTS, json=fields)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _link(http: TestClient, project_id: str, full_name: str) -> httpx.Response:
    return http.post(f"{PROJECTS}/{project_id}/repository", json={"full_name": full_name})


def _error(resp: httpx.Response, status: int, code: str) -> dict:
    assert resp.status_code == status, resp.text
    error = resp.json()["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    assert error["code"] == code
    assert error["request_id"] == resp.headers["X-Request-ID"]
    return error


def _links(db: Session) -> list[tuple]:
    return list(
        db.execute(
            select(
                ProjectRepository.project_id,
                ProjectRepository.owner_id,
                GitHubRepository.github_repo_id,
                ProjectRepository.relation,
                ProjectRepository.relation_checked_at,
            )
            .join(GitHubRepository, GitHubRepository.id == ProjectRepository.github_repository_id)
            .order_by(ProjectRepository.created_at)
        )
    )


def _repository_rows(db: Session, github_repo_id: int) -> list[tuple]:
    return list(
        db.execute(
            select(
                GitHubRepository.full_name,
                GitHubRepository.description,
                GitHubRepository.languages,
                GitHubRepository.unavailable_since,
            ).where(GitHubRepository.github_repo_id == github_repo_id)
        )
    )


# Relation.


def test_own_repository_is_linked_as_owner(env, db_session):
    env.github.add(_repo(1, description="Payments API"))
    project_id = _create(env.http, title="Payments")

    resp = _link(env.http, project_id, f"{LOGIN}/repo-1")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["id"], body["title"], body["status"], body["visibility"]) == (
        project_id,
        "Payments",
        "DRAFT",
        "PRIVATE",
    )
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
    assert env.http.get(f"{PROJECTS}/{project_id}").json()["github"] == body["github"]
    assert [r.url.path for r in env.github.requests] == [f"/repos/{LOGIN}/repo-1"]
    assert env.budget.spent(env.user.id, T0) == 1
    assert _links(db_session) == [(uuid.UUID(project_id), env.user.id, 1, "OWNER", T0)]
    assert _repository_rows(db_session, 1) == [(f"{LOGIN}/repo-1", "Payments API", None, None)]


def test_contributor_is_found_by_numeric_id_across_pages(env, db_session):
    env.github.add(
        _repo(2, owner=STRANGER, owner_id=STRANGER_ID), contributors=[[1, 2], [3, GITHUB_ID]]
    )
    project_id = _create(env.http)

    resp = _link(env.http, project_id, f"{STRANGER}/repo-2")

    assert resp.status_code == 200, resp.text
    assert resp.json()["github"]["relation"] == "CONTRIBUTOR"
    assert [r.url.path for r in env.github.requests] == [
        f"/repos/{STRANGER}/repo-2",
        f"/repos/{STRANGER}/repo-2/contributors",
        f"/repos/{STRANGER}/repo-2/contributors",
    ]
    assert env.budget.spent(env.user.id, T0) == 3
    assert _links(db_session)[0][3] == "CONTRIBUTOR"


@pytest.mark.parametrize(
    "contributors",
    [
        [[1, 2], [3]],
        # The developer's login under another id is not the developer.
        [[GITHUB_ID + 1]],
        # Only the first five pages are read (ADR-017).
        [[100 + page] for page in range(5)] + [[GITHUB_ID]],
        None,  # 204: an empty repository has no contributors
    ],
    ids=["absent", "other-id", "beyond-five-pages", "empty"],
)
def test_neither_owner_nor_contributor_is_refused(env, db_session, contributors):
    env.github.add(_repo(3, owner=STRANGER, owner_id=STRANGER_ID), contributors=contributors)
    project_id = _create(env.http)

    resp = _link(env.http, project_id, f"{STRANGER}/repo-3")

    error = _error(resp, 422, "GITHUB_RELATION_NOT_FOUND")
    assert error["details"] == {}
    assert "contributor" in error["message"]
    assert len(env.github.requests) <= 6
    assert _links(db_session) == []
    assert _repository_rows(db_session, 3) == []


def test_contributor_list_is_not_stored(env, db_session):
    env.github.add(_repo(2, owner=STRANGER, owner_id=STRANGER_ID), contributors=[[7, GITHUB_ID]])
    project_id = _create(env.http)

    assert _link(env.http, project_id, f"{STRANGER}/repo-2").status_code == 200

    tables = db_session.execute(
        text("SELECT tablename FROM pg_tables WHERE tablename LIKE '%contributor%'")
    ).all()
    assert tables == []


def test_github_is_called_outside_any_transaction(env):
    env.github.add(_repo(2, owner=STRANGER, owner_id=STRANGER_ID), contributors=[[GITHUB_ID]])
    project_id = _create(env.http)

    assert _link(env.http, project_id, f"{STRANGER}/repo-2").status_code == 200

    assert env.in_transaction == [False, False]


# Forks, archived and renamed repositories.


def test_fork_and_archived_repository_keep_their_flags(env):
    env.github.add(
        _repo(4, fork=True, archived=True, parent={"full_name": "upstream/lib", "id": 9})
    )
    project_id = _create(env.http)

    github = _link(env.http, project_id, f"{LOGIN}/repo-4").json()["github"]

    assert (github["is_fork"], github["parent_full_name"], github["is_archived"]) == (
        True,
        "upstream/lib",
        True,
    )


def test_old_name_is_read_by_the_id_github_points_to(env, db_session):
    env.github.add(_repo(5, name="new-name"))
    env.github.moved[f"{LOGIN}/old-name"] = 5
    project_id = _create(env.http)

    resp = _link(env.http, project_id, f"{LOGIN}/old-name")

    assert resp.status_code == 200, resp.text
    assert resp.json()["github"]["full_name"] == f"{LOGIN}/new-name"
    assert [r.url.path for r in env.github.requests] == [
        f"/repos/{LOGIN}/old-name",
        "/repositories/5",
    ]
    assert env.budget.spent(env.user.id, T0) == 2


# Projects: ownership, ids, states.


def test_foreign_project_is_not_found(env, make_auth_client, db_session):
    other, _ = _other_user(make_auth_client, db_session)
    foreign = _create(other)
    env.github.add(_repo(1))

    resp = _link(env.http, foreign, f"{LOGIN}/repo-1")

    _error(resp, 404, "NOT_FOUND")
    assert env.github.requests == []
    _error(env.http.delete(f"{PROJECTS}/{foreign}/repository"), 404, "NOT_FOUND")


@pytest.mark.parametrize(
    "project_id",
    [
        "not-a-uuid",
        "{00000000-0000-0000-0000-000000000001}",
        "00000000000000000000000000000001",
        str(uuid.uuid4()),
    ],
    ids=["garbage", "braces", "no-dashes", "missing"],
)
def test_malformed_or_missing_project_id_is_not_found(env, project_id):
    env.github.add(_repo(1))

    _error(_link(env.http, project_id, f"{LOGIN}/repo-1"), 404, "NOT_FOUND")
    _error(env.http.delete(f"{PROJECTS}/{project_id}/repository"), 404, "NOT_FOUND")
    assert env.github.requests == []


def test_uppercase_project_id_is_the_same_project(env):
    # Canonical in either case, as for every project path.
    env.github.add(_repo(1))
    project_id = _create(env.http)

    resp = _link(env.http, project_id.upper(), f"{LOGIN}/repo-1")

    assert (resp.status_code, resp.json()["id"]) == (200, project_id)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"full_name": ""},
        {"full_name": "octocat"},
        {"full_name": "octocat/"},
        {"full_name": "octocat/a/b"},
        {"full_name": "-octocat/x"},
        {"full_name": "octocat/.."},
        {"full_name": "octocat/."},
        {"full_name": "octo cat/x"},
        {"full_name": "https://github.com/octocat/x"},
        {"full_name": "octocat/" + "x" * 101},
        {"full_name": 1},
        {"full_name": f"{LOGIN}/repo-1", "relation": "OWNER"},
    ],
)
def test_invalid_body_is_refused_before_github(env, body):
    project_id = _create(env.http)

    resp = env.http.post(f"{PROJECTS}/{project_id}/repository", json=body)

    _error(resp, 422, "VALIDATION_ERROR")
    assert env.github.requests == []


def test_state_changes_keep_the_link_and_any_state_can_be_linked(env):
    env.github.add(_repo(1))
    env.github.add(_repo(2))
    project_id = _create(
        env.http,
        title="Payments API",
        summary="Card payments",
        role="Backend developer",
        contribution="Built it",
        technologies=["Python"],
    )
    assert _link(env.http, project_id, f"{LOGIN}/repo-1").json()["status"] == "DRAFT"

    # Linking changes no state, and no state change touches the link (ADR-017).
    for action, body, status, visibility in [
        ("publish", None, "PUBLISHED", "PUBLIC"),
        ("visibility", {"visibility": "PRIVATE"}, "PUBLISHED", "PRIVATE"),
        ("archive", None, "ARCHIVED", "PRIVATE"),
    ]:
        resp = env.http.post(f"{PROJECTS}/{project_id}/{action}", json=body)
        assert resp.status_code == 200, resp.text
        assert (resp.json()["status"], resp.json()["visibility"]) == (status, visibility)
        assert resp.json()["github"]["github_repo_id"] == 1

    relinked = _link(env.http, project_id, f"{LOGIN}/repo-2")
    assert relinked.status_code == 200, relinked.text
    assert (relinked.json()["status"], relinked.json()["github"]["github_repo_id"]) == (
        "ARCHIVED",
        2,
    )


def test_deleting_the_project_removes_the_link_and_keeps_the_repository(env, db_session):
    env.github.add(_repo(1))
    project_id = _create(env.http)
    _link(env.http, project_id, f"{LOGIN}/repo-1")

    assert env.http.delete(f"{PROJECTS}/{project_id}").status_code == 204

    assert _links(db_session) == []
    assert len(_repository_rows(db_session, 1)) == 1


# Linking again, replacing, conflicts.


def test_same_repository_again_rechecks_the_relation(env, db_session):
    env.github.add(_repo(2, owner=STRANGER, owner_id=STRANGER_ID), contributors=[[GITHUB_ID]])
    project_id = _create(env.http)
    _link(env.http, project_id, f"{STRANGER}/repo-2")

    env.clock.now = T0 + timedelta(minutes=5)
    env.github.by_name[f"{STRANGER}/repo-2"]["description"] = "Updated"
    resp = _link(env.http, project_id, f"{STRANGER}/repo-2")

    assert resp.status_code == 200, resp.text
    assert resp.json()["github"]["description"] == "Updated"
    assert _links(db_session) == [
        (uuid.UUID(project_id), env.user.id, 2, "CONTRIBUTOR", T0 + timedelta(minutes=5))
    ]
    assert len(_repository_rows(db_session, 2)) == 1


def test_linking_another_repository_replaces_the_link(env, db_session):
    env.github.add(_repo(1))
    env.github.add(_repo(2))
    project_id = _create(env.http)
    _link(env.http, project_id, f"{LOGIN}/repo-1")

    resp = _link(env.http, project_id, f"{LOGIN}/repo-2")

    assert resp.json()["github"]["github_repo_id"] == 2
    assert [link[2] for link in _links(db_session)] == [2]
    assert len(_repository_rows(db_session, 1)) == 1


def test_repository_linked_to_another_own_project_is_a_conflict(env, db_session):
    env.github.add(_repo(1, description="Before"))
    first = _create(env.http)
    second = _create(env.http)
    _link(env.http, first, f"{LOGIN}/repo-1")
    env.github.by_name[f"{LOGIN}/repo-1"]["description"] = "After"

    resp = _link(env.http, second, f"{LOGIN}/repo-1")

    error = _error(resp, 409, "GITHUB_REPOSITORY_ALREADY_LINKED")
    assert error["details"] == {"project_id": first}
    # The failed request left nothing behind: the shared row kept its data.
    assert _links(db_session) == [(uuid.UUID(first), env.user.id, 1, "OWNER", T0)]
    assert _repository_rows(db_session, 1) == [(f"{LOGIN}/repo-1", "Before", None, None)]
    assert env.http.get(f"{PROJECTS}/{second}").json()["github"] is None


def test_two_users_share_one_repository_row(env, make_auth_client, db_session):
    env.github.add(_repo(1), contributors=[[OTHER_GITHUB_ID]])
    other, other_user = _other_user(make_auth_client, db_session)

    mine = _link(env.http, _create(env.http), f"{LOGIN}/repo-1")
    theirs = _link(other, _create(other), f"{LOGIN}/repo-1")

    assert (mine.json()["github"]["relation"], theirs.json()["github"]["relation"]) == (
        "OWNER",
        "CONTRIBUTOR",
    )
    assert len(_repository_rows(db_session, 1)) == 1
    assert {(link[1], link[3]) for link in _links(db_session)} == {
        (env.user.id, "OWNER"),
        (other_user.id, "CONTRIBUTOR"),
    }


def test_link_clears_unavailable_since(env, db_session):
    env.github.add(_repo(1))
    project_id = _create(env.http)
    _link(env.http, project_id, f"{LOGIN}/repo-1")
    db_session.execute(
        GitHubRepository.__table__.update()
        .where(GitHubRepository.github_repo_id == 1)
        .values(unavailable_since=T0)
    )
    db_session.commit()
    assert env.http.get(f"{PROJECTS}/{project_id}").json()["github"]["unavailable"] is True

    assert _link(env.http, project_id, f"{LOGIN}/repo-1").json()["github"]["unavailable"] is False


def test_languages_are_ordered_by_bytes(env, db_session):
    env.github.add(_repo(1))
    project_id = _create(env.http)
    _link(env.http, project_id, f"{LOGIN}/repo-1")
    db_session.execute(
        GitHubRepository.__table__.update()
        .where(GitHubRepository.github_repo_id == 1)
        .values(languages={"Shell": 10, "Python": 900, "Go": 10})
    )
    db_session.commit()

    languages = env.http.get(f"{PROJECTS}/{project_id}").json()["github"]["languages"]

    assert languages == [
        {"name": "Python", "bytes": 900},
        {"name": "Go", "bytes": 10},
        {"name": "Shell", "bytes": 10},
    ]


# Unlinking.


def test_unlink_removes_the_link_and_keeps_the_repository(env, db_session):
    env.github.add(_repo(1))
    project_id = _create(env.http)
    _link(env.http, project_id, f"{LOGIN}/repo-1")

    first = env.http.delete(f"{PROJECTS}/{project_id}/repository")
    second = env.http.delete(f"{PROJECTS}/{project_id}/repository")

    assert first.status_code == second.status_code == 200
    assert first.json()["github"] is None
    assert first.json() == second.json()
    assert _links(db_session) == []
    assert len(_repository_rows(db_session, 1)) == 1


def test_unlink_needs_the_frontend_origin(env, make_auth_client):
    project_id = _create(env.http)
    no_origin = _new_client(make_auth_client, send_origin=False)
    no_origin.cookies = env.http.cookies

    _error(no_origin.delete(f"{PROJECTS}/{project_id}/repository"), 403, "CSRF_ORIGIN_INVALID")
    _error(
        no_origin.post(f"{PROJECTS}/{project_id}/repository", json={"full_name": "a/b"}),
        403,
        "CSRF_ORIGIN_INVALID",
    )


def test_requires_a_session(env, make_auth_client):
    anonymous = _new_client(make_auth_client)

    _error(
        anonymous.post(f"{PROJECTS}/{uuid.uuid4()}/repository", json={"full_name": "a/b"}),
        401,
        "UNAUTHORIZED",
    )
    _error(anonymous.delete(f"{PROJECTS}/{uuid.uuid4()}/repository"), 401, "UNAUTHORIZED")
    assert env.github.requests == []


# Budget, pause and GitHub errors: nothing is stored.


def test_exhausted_user_budget_is_refused_before_github(env, db_session):
    env.github.add(_repo(1))
    project_id = _create(env.http)
    # 6 left: a link reserves 7, its worst case with a redirect (ADR-018).
    env.budget.charge(env.user.id, 54, T0 - timedelta(minutes=45))

    resp = _link(env.http, project_id, f"{LOGIN}/repo-1")

    error = _error(resp, 429, "GITHUB_USER_LIMIT_REACHED")
    assert error["details"] == {"retry_after_seconds": 900}
    assert resp.headers["Retry-After"] == "900"
    assert env.github.requests == []
    assert _links(db_session) == []


def test_platform_pause_is_503_without_calling_github(env, db_session):
    env.github.add(_repo(1))
    project_id = _create(env.http)
    env.pause.start(T0 + timedelta(seconds=45))

    resp = _link(env.http, project_id, f"{LOGIN}/repo-1")

    assert _error(resp, 503, "GITHUB_RATE_LIMITED")["details"] == {"retry_after_seconds": 45}
    assert resp.headers["Retry-After"] == "45"
    assert env.github.requests == []
    assert env.budget.spent(env.user.id, T0) == 0
    assert _links(db_session) == []


@pytest.mark.parametrize("repo", [_repo(1, private=True), None], ids=["private", "404"])
def test_missing_or_private_repository_is_not_found(env, db_session, repo):
    if repo is not None:
        env.github.add(repo)
    project_id = _create(env.http)

    resp = _link(env.http, project_id, f"{LOGIN}/repo-1")

    assert _error(resp, 422, "GITHUB_REPOSITORY_NOT_FOUND")["details"] == {}
    assert _links(db_session) == []
    assert _repository_rows(db_session, 1) == []


def _timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timed out", request=request)


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
    env.github.add(_repo(1, owner=STRANGER, owner_id=STRANGER_ID, name="repo-1"))
    env.github.respond = respond
    project_id = _create(env.http)

    resp = _link(env.http, project_id, f"{STRANGER}/repo-1")

    assert _error(resp, 502, "GITHUB_UNAVAILABLE")["details"] == {}
    assert BODY_MARKER not in resp.text
    assert _links(db_session) == []
    assert _repository_rows(db_session, 1) == []


# Races between two real transactions (as in step 3.2b).


class TestRaces:
    def _seed(self, db_engine, users: int) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
        """Users with one project each, plus a second project for the first user."""
        user_ids, project_ids = [], []
        with Session(db_engine) as db:
            for _ in range(users):
                user = User(
                    github_user_id=900_000 + uuid.uuid4().int % 100_000,
                    github_login=f"race-{uuid.uuid4().hex[:8]}",
                )
                db.add(user)
                db.flush()
                user_ids.append(user.id)
                project = Project(owner_id=user.id)
                db.add(project)
                db.flush()
                project_ids.append(project.id)
            second = Project(owner_id=user_ids[0])
            db.add(second)
            db.flush()
            project_ids.append(second.id)
            db.commit()
        return user_ids, project_ids

    def _cleanup(self, db_engine, user_ids: list[uuid.UUID], github_repo_id: int) -> None:
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": user_ids})
            conn.execute(
                text("DELETE FROM github_repositories WHERE github_repo_id = :id"),
                {"id": github_repo_id},
            )

    def _checked(self, github_repo_id: int, relation: str) -> github_service.CheckedRepository:
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
            relation,
        )

    # The same steps and lock order as the route's write transaction.
    def _store(self, db: Session, user_id, project_id, github_repo_id: int) -> None:
        user = db.get(User, user_id)
        project = project_service.get_own_project(db, user, str(project_id), for_update=True)
        github_service.store_link(db, project, self._checked(github_repo_id, "OWNER"), T0)

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

    def _rows(self, db_engine, github_repo_id: int) -> tuple[int, list[uuid.UUID]]:
        with db_engine.connect() as conn:
            repositories = conn.execute(
                select(func.count())
                .select_from(GitHubRepository)
                .where(GitHubRepository.github_repo_id == github_repo_id)
            ).scalar_one()
            projects = conn.execute(
                select(ProjectRepository.project_id)
                .join(
                    GitHubRepository, GitHubRepository.id == ProjectRepository.github_repository_id
                )
                .where(GitHubRepository.github_repo_id == github_repo_id)
            ).scalars()
            return repositories, list(projects)

    @pytest.mark.parametrize("first_outcome", ["commit", "rollback"])
    def test_one_repository_to_two_own_projects(self, db_engine, first_outcome):
        repo_id = 800_000_000 + uuid.uuid4().int % 1_000_000
        (user_id,), (first_project, second_project) = self._seed(db_engine, users=1)
        try:
            result = self._race(
                db_engine,
                lambda db: self._store(db, user_id, first_project, repo_id),
                lambda db: self._store(db, user_id, second_project, repo_id),
                first_outcome,
            )
            repositories, projects = self._rows(db_engine, repo_id)
            assert repositories == 1
            if first_outcome == "commit":
                assert isinstance(result.get("error"), AppError), result
                assert result["error"].code == "GITHUB_REPOSITORY_ALREADY_LINKED"
                assert result["error"].details == {"project_id": str(first_project)}
                assert projects == [first_project]
            else:
                assert result == {"ok": True}
                assert projects == [second_project]
        finally:
            self._cleanup(db_engine, [user_id], repo_id)

    def test_one_new_repository_to_two_users(self, db_engine):
        repo_id = 800_000_000 + uuid.uuid4().int % 1_000_000
        (first_user, second_user), (first_project, second_project, _) = self._seed(
            db_engine, users=2
        )
        try:
            result = self._race(
                db_engine,
                lambda db: self._store(db, first_user, first_project, repo_id),
                lambda db: self._store(db, second_user, second_project, repo_id),
                "commit",
            )
            assert result == {"ok": True}
            repositories, projects = self._rows(db_engine, repo_id)
            assert repositories == 1
            assert sorted(projects) == sorted([first_project, second_project])
        finally:
            self._cleanup(db_engine, [first_user, second_user], repo_id)
