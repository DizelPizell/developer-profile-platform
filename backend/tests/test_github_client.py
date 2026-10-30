"""GitHub API client (ADR-016): requests, parsing and errors, without network."""

import base64
import json
import logging
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from app.github.client import (
    GitHubApiClient,
    GitHubCredentialsRejected,
    GitHubError,
    GitHubMoved,
    GitHubNotFound,
    GitHubRateLimited,
    GitHubRepositoryData,
    GitHubRepositoryListEntry,
    GitHubUnavailable,
    GitHubUnexpected,
    InvalidGitHubInput,
    RateLimit,
    RateLimitPause,
    RateLimitState,
)

FIXTURES = Path(__file__).parent / "fixtures" / "github"
CLIENT_ID = "Iv1.CLIENTIDMARKER"
CLIENT_SECRET = "SECRET_CLIENT_SECRET_MARKER"
BODY_MARKER = "SECRET_RESPONSE_BODY_MARKER"
NOW = datetime(2026, 10, 30, 12, 0, 0)

Handler = Callable[[httpx.Request], httpx.Response]


def _fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _epoch(moment: datetime) -> int:
    # Naive UTC → Unix seconds.
    return int((moment - datetime(1970, 1, 1)).total_seconds())


def _rate_headers(remaining: int = 4999, reset: datetime | None = None) -> dict[str, str]:
    return {
        "x-ratelimit-limit": "5000",
        "x-ratelimit-remaining": str(remaining),
        "x-ratelimit-reset": str(_epoch(reset or NOW + timedelta(minutes=30))),
        "x-ratelimit-used": str(5000 - remaining),
        "x-ratelimit-resource": "core",
    }


class Recorder:
    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def _client(handler: Handler, state: RateLimitState | None = None):
    recorder = Recorder(handler)
    http = httpx.Client(transport=httpx.MockTransport(recorder))
    client = GitHubApiClient(
        http,
        CLIENT_ID,
        CLIENT_SECRET,
        rate_limits=state or RateLimitState(),
        pause=RateLimitPause(),
        now=lambda: NOW,
    )
    return client, recorder


def _json(status: int, body: object, headers: dict[str, str] | None = None) -> Handler:
    return lambda request: httpx.Response(status, json=body, headers=headers or _rate_headers())


# Successful answers.


def test_get_repository_reads_documented_fields():
    client, recorder = _client(_json(200, _fixture("repository.json")))

    repo = client.get_repository("octocat", "Hello-World")

    assert recorder.requests[0].url == "https://api.github.com/repos/octocat/Hello-World"
    assert repo.github_repo_id == 1296269
    assert repo.owner_github_id == 583231
    assert (repo.owner_login, repo.name, repo.full_name) == (
        "octocat",
        "Hello-World",
        "octocat/Hello-World",
    )
    assert repo.html_url == "https://github.com/octocat/Hello-World"
    assert repo.description == "This your first repo!"
    assert (repo.is_fork, repo.is_archived, repo.parent_full_name) == (False, False, None)
    assert repo.pushed_at == datetime(2011, 1, 26, 19, 6, 43)


def test_get_repository_by_id_uses_numeric_path():
    client, recorder = _client(_json(200, _fixture("repository.json")))

    repo = client.get_repository_by_id(1296269)

    assert recorder.requests[0].url == "https://api.github.com/repositories/1296269"
    assert repo.full_name == "octocat/Hello-World"


def test_fork_carries_parent():
    client, _ = _client(_json(200, _fixture("repository_fork.json")))

    repo = client.get_repository("dev-user", "Hello-World")

    assert repo.is_fork
    assert repo.parent_full_name == "octocat/Hello-World"


def test_archived_and_empty_repositories():
    archived, _ = _client(_json(200, _fixture("repository_archived.json")))
    empty, _ = _client(_json(200, _fixture("repository_empty.json")))

    assert archived.get_repository("octocat", "old-project").is_archived
    repo = empty.get_repository("octocat", "empty")
    assert repo.pushed_at is None
    assert repo.description is None


def test_extra_fields_are_dropped_and_odd_html_url_is_rebuilt():
    body = dict(
        _fixture("repository.json"),
        html_url="javascript:alert(1)",
        topics=["x"],
        secret_field=BODY_MARKER,
    )
    client, _ = _client(_json(200, body))

    repo = client.get_repository("octocat", "Hello-World")

    assert repo.html_url == "https://github.com/octocat/Hello-World"
    assert BODY_MARKER not in repr(repo)


def test_private_repository_is_not_found():
    client, _ = _client(_json(200, dict(_fixture("repository.json"), private=True)))

    with pytest.raises(GitHubNotFound):
        client.get_repository("octocat", "Hello-World")


def test_list_user_repositories_requests_owner_repos_by_push_date():
    link = '<https://api.github.com/user/583231/repos?page=2>; rel="next"'
    client, recorder = _client(
        lambda r: httpx.Response(
            200, json=_fixture("user_repositories.json"), headers={"link": link}
        )
    )

    page = client.list_user_repositories("octocat", 1)

    request = recorder.requests[0]
    assert request.url.path == "/users/octocat/repos"
    assert dict(request.url.params) == {
        "type": "owner",
        "sort": "pushed",
        "direction": "desc",
        "per_page": "100",
        "page": "1",
    }
    assert [item.github_repo_id for item in page.items] == [1296269, 2000002]
    assert page.items[1].is_archived
    assert page.has_next


def test_list_without_next_link_is_last_page():
    client, _ = _client(_json(200, []))

    page = client.list_user_repositories("octocat", 3)

    assert page.items == ()
    assert not page.has_next


def test_get_languages_keeps_github_shape():
    client, recorder = _client(_json(200, _fixture("languages.json")))

    assert client.get_languages("octocat", "Hello-World") == {"C": 78769, "Python": 7769}
    assert recorder.requests[0].url.path == "/repos/octocat/Hello-World/languages"


def test_contributor_page_returns_ids():
    client, recorder = _client(_json(200, _fixture("contributors.json")))

    page = client.get_contributor_page("octocat", "Hello-World", 1)

    assert page.github_user_ids == (583231, 4000001)
    assert not page.has_next
    assert dict(recorder.requests[0].url.params) == {"per_page": "100", "page": "1"}
    assert "anon" not in recorder.requests[0].url.params


def test_contributors_204_is_an_empty_page():
    client, _ = _client(lambda r: httpx.Response(204, headers=_rate_headers()))

    page = client.get_contributor_page("octocat", "empty", 1)

    assert page.github_user_ids == ()
    assert not page.has_next


def _contributor_pages(found_on: int | None) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        ids = [4000001] if page == found_on else [page * 10]
        return httpx.Response(
            200,
            json=[{"id": i, "login": f"u{i}", "type": "User"} for i in ids],
            headers={"link": f'<https://api.github.com/x?page={page + 1}>; rel="next"'},
        )

    return handler


def test_is_contributor_stops_when_found():
    client, recorder = _client(_contributor_pages(found_on=2))

    assert client.is_contributor("octocat", "Hello-World", 4000001)
    assert len(recorder.requests) == 2
    assert client.requests_sent == 2


def test_is_contributor_reads_at_most_five_pages():
    client, recorder = _client(_contributor_pages(found_on=6))

    assert not client.is_contributor("octocat", "Hello-World", 4000001)
    assert len(recorder.requests) == 5


def test_is_contributor_stops_on_last_page():
    client, recorder = _client(_json(200, _fixture("contributors.json")))

    assert not client.is_contributor("octocat", "Hello-World", 999)
    assert len(recorder.requests) == 1


# Malformed bodies are treated like an unavailable GitHub (ADR-018).


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"id": 1},
        dict(_fixture("repository.json"), id="1296269"),
        dict(_fixture("repository.json"), id=True),
        dict(_fixture("repository.json"), id=0),
        dict(_fixture("repository.json"), full_name="someone/else"),
        dict(_fixture("repository.json"), name=" "),
        dict(_fixture("repository.json"), fork="false"),
        dict(_fixture("repository.json"), pushed_at="2011-01-26T19:06:43"),
        dict(_fixture("repository.json"), description=5),
        dict(_fixture("repository.json"), owner=None),
    ],
    ids=[
        "list",
        "missing-fields",
        "string-id",
        "bool-id",
        "zero-id",
        "full-name-mismatch",
        "blank-name",
        "string-fork",
        "naive-timestamp",
        "numeric-description",
        "no-owner",
    ],
)
def test_malformed_repository_is_unavailable(body):
    client, _ = _client(_json(200, body))

    with pytest.raises(GitHubUnavailable) as exc:
        client.get_repository("octocat", "Hello-World")
    assert exc.value.reason == "malformed_response"


@pytest.mark.parametrize("body", [[], {"C": "1"}, {"C": -1}, {"C": True}, {" ": 1}])
def test_malformed_languages_are_unavailable(body):
    client, _ = _client(_json(200, body))

    with pytest.raises(GitHubUnavailable):
        client.get_languages("octocat", "Hello-World")


def test_non_json_body_is_unavailable():
    client, _ = _client(lambda r: httpx.Response(200, text=f"<html>{BODY_MARKER}"))

    with pytest.raises(GitHubUnavailable) as exc:
        client.get_repository("octocat", "Hello-World")
    assert BODY_MARKER not in str(exc.value)


# Error statuses.


def test_404_is_not_found():
    client, _ = _client(_json(404, {"message": "Not Found"}))

    with pytest.raises(GitHubNotFound):
        client.get_repository("octocat", "missing")


@pytest.mark.parametrize("status", [403, 429])
def test_exhausted_primary_limit_waits_until_reset(status):
    reset = NOW + timedelta(minutes=17)
    client, _ = _client(
        _json(status, {"message": "API rate limit exceeded"}, _rate_headers(0, reset))
    )

    with pytest.raises(GitHubRateLimited) as exc:
        client.get_repository("octocat", "Hello-World")
    assert exc.value.retry_at == reset


@pytest.mark.parametrize("status", [403, 429])
def test_retry_after_is_honoured(status):
    client, _ = _client(
        _json(status, {"message": "slow down"}, dict(_rate_headers(), **{"retry-after": "120"}))
    )

    with pytest.raises(GitHubRateLimited) as exc:
        client.get_repository("octocat", "Hello-World")
    assert exc.value.retry_at == NOW + timedelta(seconds=120)


def test_secondary_limit_message_waits_a_minute():
    message = "You have exceeded a secondary rate limit. Please wait a few minutes."
    client, _ = _client(_json(403, {"message": message}))

    with pytest.raises(GitHubRateLimited) as exc:
        client.get_repository("octocat", "Hello-World")
    assert exc.value.retry_at == NOW + timedelta(seconds=60)


def test_429_without_headers_waits_a_minute():
    client, _ = _client(lambda r: httpx.Response(429))

    with pytest.raises(GitHubRateLimited) as exc:
        client.get_repository("octocat", "Hello-World")
    assert exc.value.retry_at == NOW + timedelta(seconds=60)


def test_exhausted_limit_with_past_reset_waits_a_minute():
    client, _ = _client(_json(403, {}, _rate_headers(0, NOW - timedelta(seconds=5))))

    with pytest.raises(GitHubRateLimited) as exc:
        client.get_repository("octocat", "Hello-World")
    assert exc.value.retry_at == NOW + timedelta(seconds=60)


def test_other_403_is_unexpected():
    client, _ = _client(_json(403, {"message": BODY_MARKER}))

    with pytest.raises(GitHubUnexpected) as exc:
        client.get_repository("octocat", "Hello-World")
    assert exc.value.status == 403
    assert not isinstance(exc.value, GitHubRateLimited)
    assert BODY_MARKER not in str(exc.value)


@pytest.mark.parametrize("status", [500, 502, 503])
def test_5xx_is_unavailable(status):
    client, _ = _client(lambda r: httpx.Response(status, text=BODY_MARKER))

    with pytest.raises(GitHubUnavailable) as exc:
        client.get_repository("octocat", "Hello-World")
    assert exc.value.status == status
    assert BODY_MARKER not in str(exc.value)


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (httpx.ReadTimeout, "timeout"),
        (httpx.ConnectTimeout, "timeout"),
        (httpx.ConnectError, "ConnectError"),
    ],
)
def test_network_failures_are_unavailable(error, reason):
    def handler(request: httpx.Request) -> httpx.Response:
        raise error("failed", request=request)

    client, _ = _client(handler)

    with pytest.raises(GitHubUnavailable) as exc:
        client.get_repository("octocat", "Hello-World")
    assert exc.value.reason == reason
    assert exc.value.__cause__ is None
    assert client.requests_sent == 1


@pytest.mark.parametrize("status", [301, 307])
def test_redirect_to_repository_id_is_moved_and_not_followed(status):
    client, recorder = _client(
        lambda r: httpx.Response(
            status, headers={"location": "https://api.github.com/repositories/1296269"}
        )
    )

    with pytest.raises(GitHubMoved) as exc:
        client.get_repository("twitter", "bootstrap")
    assert exc.value.repository_id == 1296269
    assert len(recorder.requests) == 1


def test_redirect_of_a_sub_resource_keeps_the_id():
    client, _ = _client(
        lambda r: httpx.Response(
            301, headers={"location": "https://api.github.com/repositories/42/languages"}
        )
    )

    with pytest.raises(GitHubMoved) as exc:
        client.get_languages("old", "name")
    assert exc.value.repository_id == 42


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.example/repositories/1",
        "http://api.github.com/repositories/1",
        "https://api.github.com.evil.example/repositories/1",
        "https://api.github.com/repos/octocat/Hello-World",
        "https://api.github.com/repositories/0",
        "https://api.github.com/repositories/99999999999999999999",
        "",
    ],
)
def test_redirect_elsewhere_is_unexpected(location):
    client, recorder = _client(lambda r: httpx.Response(301, headers={"location": location}))

    with pytest.raises(GitHubUnexpected):
        client.get_repository("octocat", "Hello-World")
    assert len(recorder.requests) == 1


def test_401_is_credentials_rejected():
    client, _ = _client(_json(401, {"message": "Bad credentials"}))

    with pytest.raises(GitHubCredentialsRejected) as exc:
        client.get_repository("octocat", "Hello-World")
    assert exc.value.status == 401


def test_other_status_is_unexpected_without_body():
    client, _ = _client(lambda r: httpx.Response(418, text=BODY_MARKER))

    with pytest.raises(GitHubUnexpected) as exc:
        client.get_repository("octocat", "Hello-World")
    assert exc.value.status == 418
    assert BODY_MARKER not in str(exc.value)


# Input is validated before any request; the host is fixed.


@pytest.mark.parametrize(
    ("owner", "name"),
    [
        ("", "repo"),
        ("-octocat", "repo"),
        ("octocat-", "repo"),
        ("a" * 40, "repo"),
        ("octo_cat", "repo"),
        ("evil.example", "repo"),
        ("octocat", ""),
        ("octocat", "."),
        ("octocat", ".."),
        ("octocat", "a/b"),
        ("octocat", "a?b"),
        ("octocat", "a%2Fb"),
        ("octocat", "a" * 101),
        ("octocat", "repo\n"),
        ("octocat", "réppo"),
    ],
)
def test_invalid_owner_or_name_sends_nothing(owner, name):
    client, recorder = _client(_json(200, _fixture("repository.json")))

    for call in (client.get_repository, client.get_languages):
        with pytest.raises(InvalidGitHubInput):
            call(owner, name)
    with pytest.raises(InvalidGitHubInput):
        client.get_contributor_page(owner, name, 1)
    assert recorder.requests == []
    assert client.requests_sent == 0


@pytest.mark.parametrize("repo_id", [0, -1, True, 2**63, "1296269"])
def test_invalid_repository_id_sends_nothing(repo_id):
    client, recorder = _client(_json(200, _fixture("repository.json")))

    with pytest.raises(InvalidGitHubInput):
        client.get_repository_by_id(repo_id)
    assert recorder.requests == []


def test_invalid_login_or_page_sends_nothing():
    client, recorder = _client(_json(200, []))

    for login, page in [("octo cat", 1), ("octocat", 0), ("octocat", 101), ("octocat", True)]:
        with pytest.raises(InvalidGitHubInput):
            client.list_user_repositories(login, page)
    for page in (0, 6):
        with pytest.raises(InvalidGitHubInput):
            client.get_contributor_page("octocat", "Hello-World", page)
    assert recorder.requests == []


def test_every_request_goes_to_api_github_com_over_https():
    bodies = {
        "/repos/octocat/Hello-World": _fixture("repository.json"),
        "/repositories/1296269": _fixture("repository.json"),
        "/users/octocat/repos": [],
        "/repos/octocat/Hello-World/languages": {},
        "/repos/octocat/Hello-World/contributors": [],
    }
    client, recorder = _client(lambda r: httpx.Response(200, json=bodies[r.url.path]))

    client.get_repository("octocat", "Hello-World")
    client.get_repository_by_id(1296269)
    client.list_user_repositories("octocat", 1)
    client.get_languages("octocat", "Hello-World")
    client.get_contributor_page("octocat", "Hello-World", 1)

    assert len(recorder.requests) == 5
    for request in recorder.requests:
        assert request.method == "GET"
        assert request.url.scheme == "https"
        assert request.url.host == "api.github.com"
        assert request.url.port is None
    assert client.requests_sent == 5


# Credentials.


def test_credentials_sent_as_basic_header_only():
    client, recorder = _client(_json(200, _fixture("repository.json")))

    client.get_repository("octocat", "Hello-World")

    request = recorder.requests[0]
    scheme, token = request.headers["authorization"].split(" ", 1)
    assert scheme == "Basic"
    assert base64.b64decode(token).decode() == f"{CLIENT_ID}:{CLIENT_SECRET}"
    assert CLIENT_SECRET not in str(request.url)
    assert CLIENT_ID not in str(request.url)
    assert request.headers["accept"] == "application/vnd.github+json"
    assert request.headers["user-agent"] == "developer-profile-platform"


@pytest.fixture
def github_log(caplog, monkeypatch):
    # alembic's fileConfig (db_engine fixture) disables loggers that existed before it ran.
    monkeypatch.setattr(logging.getLogger("app.github.client"), "disabled", False)
    caplog.set_level(logging.DEBUG, logger="app.github.client")
    return caplog


def _timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout(f"timed out {BODY_MARKER}", request=request)


@pytest.mark.parametrize(
    "handler",
    [
        _json(200, dict(_fixture("repository.json"), description=BODY_MARKER)),
        _json(404, {"message": BODY_MARKER}),
        _json(403, {"message": BODY_MARKER}, _rate_headers(0)),
        _json(403, {"message": BODY_MARKER}),
        lambda r: httpx.Response(500, text=BODY_MARKER),
        lambda r: httpx.Response(200, text=BODY_MARKER),
        lambda r: httpx.Response(301, headers={"location": f"https://x/{BODY_MARKER}"}),
        _timeout,
    ],
    ids=["ok", "404", "limit", "403", "500", "not-json", "redirect", "timeout"],
)
def test_secrets_and_bodies_stay_out_of_logs_errors_and_repr(github_log, handler):
    client, _ = _client(handler)

    error: GitHubError | None = None
    try:
        client.get_repository("octocat", "Hello-World")
    except GitHubError as exc:
        error = exc

    texts = [record.getMessage() for record in github_log.records] + [repr(client)]
    if error is not None:
        texts += [str(error), repr(error)]
    for text in texts:
        for secret in (CLIENT_SECRET, CLIENT_ID, base64.b64encode(CLIENT_SECRET.encode()).decode()):
            assert secret not in text
        assert BODY_MARKER not in text
        # No URL or path: only the operation label, the status and remaining.
        assert "octocat" not in text
        assert "api.github.com/" not in text
    assert github_log.records


def test_log_line_has_operation_status_and_remaining(github_log):
    client, _ = _client(_json(200, _fixture("repository.json"), _rate_headers(4321)))

    client.get_repository("octocat", "Hello-World")

    assert [r.getMessage() for r in github_log.records] == [
        "GitHub repository: status 200, remaining 4321"
    ]


# Rate-limit headers.


def test_rate_limit_headers_are_shared_through_the_state():
    state = RateLimitState()
    reset = NOW + timedelta(minutes=30)
    client, _ = _client(_json(200, _fixture("repository.json"), _rate_headers(4321, reset)), state)

    client.get_repository("octocat", "Hello-World")

    latest = state.latest
    assert latest is not None
    assert (latest.limit, latest.remaining, latest.used, latest.resource) == (
        5000,
        4321,
        679,
        "core",
    )
    assert latest.reset_at == reset


def test_invalid_rate_limit_headers_are_ignored():
    state = RateLimitState()
    headers = {"x-ratelimit-remaining": "-1", "x-ratelimit-reset": "soon"}
    client, _ = _client(_json(200, _fixture("repository.json"), headers), state)

    client.get_repository("octocat", "Hello-World")

    assert state.latest is None


def _state_value(remaining: int | None, reset: datetime) -> RateLimit:
    return RateLimit(limit=5000, remaining=remaining, reset_at=reset, used=None, resource="core")


def test_rate_limit_state_keeps_the_lowest_remaining_of_a_window():
    state = RateLimitState()
    reset = NOW + timedelta(minutes=30)

    state.update(_state_value(480, reset))
    state.update(_state_value(520, reset))  # an older response processed late
    assert state.latest.remaining == 480

    state.update(_state_value(470, reset))
    assert state.latest.remaining == 470


def test_rate_limit_state_ignores_an_older_window_and_takes_a_newer_one():
    state = RateLimitState()
    reset = NOW + timedelta(minutes=30)
    state.update(_state_value(10, reset))

    state.update(_state_value(3, reset - timedelta(hours=1)))
    assert state.latest.reset_at == reset

    state.update(_state_value(4999, reset + timedelta(hours=1)))
    assert state.latest.remaining == 4999


# Review fixes: bounded waits, list items, list entry type.


@pytest.mark.parametrize("retry_after", ["7200", "999999999999", "9" * 40])
def test_retry_after_is_capped_at_an_hour(retry_after):
    client, _ = _client(_json(429, {}, {"retry-after": retry_after}))

    with pytest.raises(GitHubRateLimited) as exc:
        client.get_repository("octocat", "Hello-World")
    assert exc.value.retry_at == NOW + timedelta(hours=1)


def test_far_reset_is_capped_at_an_hour():
    client, _ = _client(_json(403, {}, _rate_headers(0, NOW + timedelta(days=400))))

    with pytest.raises(GitHubRateLimited) as exc:
        client.get_repository("octocat", "Hello-World")
    assert exc.value.retry_at == NOW + timedelta(hours=1)


def test_list_skips_private_and_malformed_items(github_log):
    good, archived = _fixture("user_repositories.json")
    body = [
        good,
        dict(good, id=3000001, private=True),
        {"id": "broken", "description": BODY_MARKER},
        archived,
    ]
    client, _ = _client(_json(200, body))

    page = client.list_user_repositories("octocat", 1)

    assert [item.github_repo_id for item in page.items] == [1296269, 2000002]
    messages = [record.getMessage() for record in github_log.records]
    assert "GitHub user_repositories: 2 items skipped" in messages
    assert all(BODY_MARKER not in message for message in messages)


def test_list_entries_carry_no_parent():
    client, _ = _client(_json(200, [_fixture("repository_fork.json")]))

    entry = client.list_user_repositories("octocat", 1).items[0]

    assert isinstance(entry, GitHubRepositoryListEntry)
    assert not isinstance(entry, GitHubRepositoryData)
    assert not hasattr(entry, "parent_full_name")


def test_client_does_not_import_the_database_layer():
    script = (
        "import sys, app.github.client; "
        "print(any(m in sys.modules for m in ('app.database', 'app.settings', 'sqlalchemy')))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
        env={"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
        check=True,
    )
    assert result.stdout.strip() == "False"
