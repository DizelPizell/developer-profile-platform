"""GET /integrations/github/repositories (ADR-017, step 5.3): the user's own public
repositories with linked_project_id, the page cache, the budget and GitHub errors."""

import base64
import logging
import re
import uuid
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.github.budget import UserRequestBudget
from app.github.client import GitHubApiClient, RateLimitPause, RateLimitState
from app.github.dependencies import (
    get_github_api_client,
    get_now,
    get_repository_page_cache,
    get_user_request_budget,
)
from app.github.page_cache import RepositoryPageCache
from app.main import app
from app.models.github import GitHubRepository, ProjectRepository
from app.models.identity import User
from app.models.projects import Project
from tests.conftest import login, make_github_transport

URL = "/api/v1/integrations/github/repositories"
T0 = datetime(2026, 10, 30, 12, 0, 0)
CLIENT_ID = "Iv1.LISTCLIENTIDMARKER"
CLIENT_SECRET = "LIST_CLIENT_SECRET_MARKER"
BODY_MARKER = "LIST_RESPONSE_BODY_MARKER"
ITEM_KEYS = {
    "github_repo_id",
    "full_name",
    "html_url",
    "description",
    "is_fork",
    "is_archived",
    "pushed_at",
    "linked_project_id",
}
# make_github_transport's default user, and a second one.
LOGIN, GITHUB_ID = "testuser", 10001
OTHER_LOGIN, OTHER_GITHUB_ID = "otheruser", 10002


def _repo(repo_id: int, owner: str = LOGIN, owner_id: int = GITHUB_ID, **fields) -> dict:
    name = f"repo-{repo_id}"
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
    """GET /users/{login}/repos from `pages`; anything else, or a missing page, is 404."""

    def __init__(self) -> None:
        self.pages: dict[tuple[str, int], list] = {}
        self.has_next: set[tuple[str, int]] = set()
        self.requests: list[httpx.Request] = []
        self.respond = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.respond is not None:
            return self.respond(request)
        match = re.fullmatch(r"/users/([^/]+)/repos", request.url.path)
        key = (match.group(1), int(request.url.params["page"])) if match else None
        if key not in self.pages:
            return httpx.Response(404, json={"message": "Not Found"})
        headers = {}
        if key in self.has_next:
            headers["link"] = f'<https://api.github.com/user/1/repos?page={key[1] + 1}>; rel="next"'
        return httpx.Response(200, json=self.pages[key], headers=headers)


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
    cache: RepositoryPageCache
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
    clock = Clock(T0)
    state = Env(
        http=http,
        github=github,
        clock=clock,
        budget=UserRequestBudget(60),
        cache=RepositoryPageCache(timedelta(seconds=300), max_pages=500),
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
                CLIENT_ID,
                CLIENT_SECRET,
                rate_limits=RateLimitState(),
                pause=state.pause,
                now=clock,
            )

    # make_auth_client clears every override at teardown.
    app.dependency_overrides[get_github_api_client] = client
    app.dependency_overrides[get_user_request_budget] = lambda: state.budget
    app.dependency_overrides[get_repository_page_cache] = lambda: state.cache
    app.dependency_overrides[get_now] = clock
    return state


def _other_user(make_auth_client, db_session: Session) -> tuple[TestClient, User]:
    http = make_auth_client(
        make_github_transport(github_user_id=OTHER_GITHUB_ID, github_login=OTHER_LOGIN)
    )
    login(http)
    user = db_session.scalar(select(User).where(User.github_user_id == OTHER_GITHUB_ID))
    return http, user


def _link(db: Session, owner: User, github_repo_id: int) -> uuid.UUID:
    """A project of `owner` linked to the repository, written straight to the database."""
    repository = db.scalar(
        select(GitHubRepository).where(GitHubRepository.github_repo_id == github_repo_id)
    )
    if repository is None:
        repository = GitHubRepository(
            github_repo_id=github_repo_id,
            owner_github_id=GITHUB_ID,
            owner_login=LOGIN,
            name=f"repo-{github_repo_id}",
            full_name=f"{LOGIN}/repo-{github_repo_id}",
            html_url=f"https://github.com/{LOGIN}/repo-{github_repo_id}",
            is_fork=False,
            is_archived=False,
        )
        db.add(repository)
    project = Project(owner_id=owner.id)
    db.add(project)
    db.flush()
    db.add(
        ProjectRepository(
            project_id=project.id,
            owner_id=owner.id,
            github_repository_id=repository.id,
            relation="OWNER",
        )
    )
    # Committed, as the application's own data is: the endpoint ends the request's
    # read transaction before calling GitHub.
    db.commit()
    return project.id


def _error(resp: httpx.Response, status: int, code: str) -> dict:
    assert resp.status_code == status, resp.text
    error = resp.json()["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    assert error["code"] == code
    assert error["request_id"] == resp.headers["X-Request-ID"]
    return error


def _ids(resp: httpx.Response) -> list[int]:
    assert resp.status_code == 200, resp.text
    return [item["github_repo_id"] for item in resp.json()["items"]]


# Session and parameters.


def test_requires_a_session(env, make_auth_client):
    anonymous = make_auth_client()

    resp = anonymous.get(URL)

    error = _error(resp, 401, "UNAUTHORIZED")
    assert error["details"] == {}
    assert env.github.requests == []


@pytest.mark.parametrize("page", ["0", "101", "abc", "1.5", ""])
def test_invalid_page_is_a_validation_error(env, page):
    resp = env.http.get(URL, params={"page": page})

    error = _error(resp, 422, "VALIDATION_ERROR")
    assert error["details"]["fields"][0]["loc"] == ["query", "page"]
    assert env.github.requests == []


# Successful pages.


def test_returns_the_page_with_contract_fields_only(env):
    env.github.pages[(LOGIN, 1)] = [
        _repo(1, description="A library", fork=True, archived=True, extra=BODY_MARKER),
        _repo(2, pushed_at=None),
    ]

    resp = env.http.get(URL)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"items", "next_page"}
    assert body["next_page"] is None
    assert [set(item) for item in body["items"]] == [ITEM_KEYS, ITEM_KEYS]
    assert body["items"][0] == {
        "github_repo_id": 1,
        "full_name": f"{LOGIN}/repo-1",
        "html_url": f"https://github.com/{LOGIN}/repo-1",
        "description": "A library",
        "is_fork": True,
        "is_archived": True,
        "pushed_at": "2026-10-01T10:00:00Z",
        "linked_project_id": None,
    }
    assert body["items"][1]["pushed_at"] is None
    assert BODY_MARKER not in resp.text
    (request,) = env.github.requests
    assert request.url.path == f"/users/{LOGIN}/repos"
    assert dict(request.url.params) == {
        "type": "owner",
        "sort": "pushed",
        "direction": "desc",
        "per_page": "100",
        "page": "1",
    }


def test_pages_follow_github_link_header(env):
    env.github.pages[(LOGIN, 1)] = [_repo(1)]
    env.github.pages[(LOGIN, 2)] = [_repo(2)]
    env.github.has_next.add((LOGIN, 1))

    first = env.http.get(URL)
    second = env.http.get(URL, params={"page": 2})

    assert (_ids(first), first.json()["next_page"]) == ([1], 2)
    assert (_ids(second), second.json()["next_page"]) == ([2], None)
    assert [r.url.params["page"] for r in env.github.requests] == ["1", "2"]


def test_private_and_malformed_items_are_skipped(env):
    env.github.pages[(LOGIN, 1)] = [
        _repo(1),
        _repo(2, private=True),
        {"id": "broken", "description": BODY_MARKER},
        _repo(3),
    ]

    resp = env.http.get(URL)

    assert _ids(resp) == [1, 3]
    assert BODY_MARKER not in resp.text


def test_items_of_another_owner_are_skipped(env):
    env.github.pages[(LOGIN, 1)] = [_repo(1), _repo(2, owner="someone", owner_id=999)]

    assert _ids(env.http.get(URL)) == [1]


# A stored login that GitHub no longer knows, or that now belongs to someone else.


@pytest.mark.parametrize(
    "page",
    [None, [_repo(1, owner=LOGIN, owner_id=999), _repo(2, owner=LOGIN, owner_id=999)]],
    ids=["404", "another-account"],
)
def test_outdated_login_is_a_conflict_and_not_cached(env, page):
    if page is not None:
        env.github.pages[(LOGIN, 1)] = page

    first = env.http.get(URL)
    second = env.http.get(URL)

    error = _error(first, 409, "GITHUB_LOGIN_OUTDATED")
    assert error["details"] == {}
    assert second.status_code == 409
    assert len(env.github.requests) == 2
    assert env.budget.spent(env.user.id, T0) == 2


# The page cache.


def test_cached_page_costs_no_request_and_no_budget(env):
    env.github.pages[(LOGIN, 1)] = [_repo(1)]

    first = env.http.get(URL)
    second = env.http.get(URL)

    assert first.json() == second.json()
    assert len(env.github.requests) == 1
    assert env.budget.spent(env.user.id, T0) == 1


def test_cached_page_expires_after_its_lifetime(env):
    env.github.pages[(LOGIN, 1)] = [_repo(1)]
    env.http.get(URL)
    env.github.pages[(LOGIN, 1)] = [_repo(1), _repo(2)]

    env.clock.now = T0 + timedelta(seconds=299)
    assert _ids(env.http.get(URL)) == [1]
    env.clock.now = T0 + timedelta(seconds=300)
    assert _ids(env.http.get(URL)) == [1, 2]

    assert len(env.github.requests) == 2


def test_pages_are_cached_separately(env):
    env.github.pages[(LOGIN, 1)] = [_repo(1)]
    env.github.pages[(LOGIN, 2)] = [_repo(2)]
    env.github.has_next.add((LOGIN, 1))

    env.http.get(URL, params={"page": 1})
    assert _ids(env.http.get(URL, params={"page": 2})) == [2]

    assert len(env.github.requests) == 2


def test_cache_is_kept_per_user(env, make_auth_client, db_session):
    env.github.pages[(LOGIN, 1)] = [_repo(1)]
    env.github.pages[(OTHER_LOGIN, 1)] = [_repo(2, owner=OTHER_LOGIN, owner_id=OTHER_GITHUB_ID)]
    other, other_user = _other_user(make_auth_client, db_session)

    assert _ids(env.http.get(URL)) == [1]
    assert _ids(other.get(URL)) == [2]
    assert _ids(env.http.get(URL)) == [1]

    assert [r.url.path for r in env.github.requests] == [
        f"/users/{LOGIN}/repos",
        f"/users/{OTHER_LOGIN}/repos",
    ]
    assert env.budget.spent(env.user.id, T0) == 1
    assert env.budget.spent(other_user.id, T0) == 1


@pytest.mark.parametrize(
    "respond",
    [
        lambda r: httpx.Response(500),
        lambda r: httpx.Response(200, json={"not": "a list"}),
    ],
    ids=["500", "malformed"],
)
def test_failed_page_is_not_cached(env, respond):
    env.github.respond = respond
    assert env.http.get(URL).status_code == 502

    env.github.respond = None
    env.github.pages[(LOGIN, 1)] = [_repo(1)]
    assert _ids(env.http.get(URL)) == [1]


# linked_project_id.


def test_linked_project_is_read_on_every_call(env, db_session):
    env.github.pages[(LOGIN, 1)] = [_repo(1), _repo(2)]
    first = env.http.get(URL)

    project_id = _link(db_session, env.user, 2)
    second = env.http.get(URL)

    assert [item["linked_project_id"] for item in first.json()["items"]] == [None, None]
    assert [item["linked_project_id"] for item in second.json()["items"]] == [
        None,
        str(project_id),
    ]
    assert len(env.github.requests) == 1


def test_links_of_other_users_are_not_shown(env, make_auth_client, db_session):
    env.github.pages[(LOGIN, 1)] = [_repo(1)]
    _, other_user = _other_user(make_auth_client, db_session)
    _link(db_session, other_user, 1)

    resp = env.http.get(URL)

    assert resp.json()["items"][0]["linked_project_id"] is None


def test_query_count_does_not_depend_on_the_page_size(env, db_session):
    def statements_for(repo_ids: range) -> int:
        env.cache = RepositoryPageCache(timedelta(seconds=300))
        env.github.pages[(LOGIN, 1)] = [_repo(repo_id) for repo_id in repo_ids]
        for repo_id in repo_ids:
            _link(db_session, env.user, repo_id)
        seen: list[str] = []

        def count(conn, cursor, statement, *args) -> None:
            seen.append(statement)

        connection = db_session.connection()
        event.listen(connection, "before_cursor_execute", count)
        try:
            resp = env.http.get(URL)
        finally:
            event.remove(connection, "before_cursor_execute", count)
        assert len(resp.json()["items"]) == len(repo_ids)
        assert all(item["linked_project_id"] for item in resp.json()["items"])
        return len(seen)

    assert statements_for(range(1, 2)) == statements_for(range(100, 130))


# Budget, pause and GitHub errors.


def test_github_is_called_outside_any_transaction(env):
    env.github.pages[(LOGIN, 1)] = [_repo(1)]
    env.github.pages[(LOGIN, 2)] = [_repo(2)]

    assert env.http.get(URL).status_code == 200
    assert env.http.get(URL, params={"page": 2}).status_code == 200

    assert env.in_transaction == [False, False]


def test_exhausted_user_budget_is_refused_before_github(env):
    env.budget.charge(env.user.id, 60, T0 - timedelta(minutes=50))

    resp = env.http.get(URL)

    error = _error(resp, 429, "GITHUB_USER_LIMIT_REACHED")
    assert error["details"] == {"retry_after_seconds": 600}
    assert resp.headers["Retry-After"] == "600"
    assert env.github.requests == []


def test_platform_pause_is_503_without_calling_github(env):
    env.pause.start(T0 + timedelta(seconds=90))

    resp = env.http.get(URL)

    error = _error(resp, 503, "GITHUB_RATE_LIMITED")
    assert error["details"] == {"retry_after_seconds": 90}
    assert resp.headers["Retry-After"] == "90"
    assert env.github.requests == []
    assert env.budget.spent(env.user.id, T0) == 0


def test_github_rate_limit_answer_is_503_and_pauses(env):
    env.github.respond = lambda r: httpx.Response(429, headers={"retry-after": "120"})

    first = env.http.get(URL)
    second = env.http.get(URL)

    assert _error(first, 503, "GITHUB_RATE_LIMITED")["details"] == {"retry_after_seconds": 120}
    assert first.headers["Retry-After"] == "120"
    assert second.status_code == 503
    assert len(env.github.requests) == 1


def _timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timed out", request=request)


@pytest.mark.parametrize(
    "respond",
    [
        _timeout,
        lambda r: httpx.Response(503, text=BODY_MARKER),
        lambda r: httpx.Response(200, text=BODY_MARKER),
        lambda r: httpx.Response(403, json={"message": BODY_MARKER}),
        lambda r: httpx.Response(
            301, headers={"location": "https://api.github.com/repositories/1"}
        ),
    ],
    ids=["timeout", "5xx", "not-json", "other-403", "redirect"],
)
def test_github_failure_is_502(env, respond):
    env.github.respond = respond

    resp = env.http.get(URL)

    error = _error(resp, 502, "GITHUB_UNAVAILABLE")
    assert error["details"] == {}
    assert BODY_MARKER not in resp.text


@pytest.fixture
def all_logs(caplog, monkeypatch):
    # alembic's fileConfig (db_engine fixture) disables loggers that existed before it ran.
    for name in ("app.errors", "app.github.service", "app.github.client"):
        monkeypatch.setattr(logging.getLogger(name), "disabled", False)
    caplog.set_level(logging.DEBUG)
    return caplog


def test_rejected_app_credentials_are_an_internal_error(env, all_logs):
    env.github.respond = lambda r: httpx.Response(401, json={"message": BODY_MARKER})

    resp = env.http.get(URL)

    error = _error(resp, 500, "INTERNAL_ERROR")
    assert (error["message"], error["details"]) == ("Internal server error", {})
    assert "GitHub rejected the app credentials" in all_logs.text
    assert error["request_id"] in all_logs.text
    basic = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    for secret in (CLIENT_ID, CLIENT_SECRET, basic, BODY_MARKER):
        assert secret not in resp.text
        assert secret not in all_logs.text
