"""The manual smoke script only reads api.github.com and prints no bodies or secrets."""

import argparse

import httpx
import pytest

from scripts import github_smoke

SECRET = "SMOKE_SECRET_MARKER"
BODY = "SMOKE_BODY_MARKER"


class FakeGitHub:
    """Counts x-ratelimit-used like GitHub: /rate_limit is free, and so is a 304
    unless spends_304."""

    def __init__(self, spends_304: bool = False) -> None:
        self.spends_304 = spends_304
        self.used = 0
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/rate_limit":
            return httpx.Response(200, json={"resources": {"core": {"limit": 5000}}, "x": BODY})
        conditional = bool(request.headers.get("if-none-match"))
        if not conditional or self.spends_304:
            self.used += 1
        headers = {
            "x-ratelimit-limit": "5000",
            "x-ratelimit-remaining": str(5000 - self.used),
            "x-ratelimit-used": str(self.used),
            "etag": '"abc"',
        }
        if path == "/repos/twitter/bootstrap":
            headers["location"] = "https://api.github.com/repositories/2126244"
            return httpx.Response(301, headers=headers)
        if conditional:
            return httpx.Response(304, headers=headers)
        if path.endswith("/contributors") and "empty" in path:
            return httpx.Response(204, headers=headers)
        if path.startswith(("/users/", "/orgs/")) or path.endswith("/contributors"):
            return httpx.Response(200, json=[{"private": False, "description": BODY}])
        if path.endswith("/readme") or "/git/trees/" in path:
            return httpx.Response(200, json={"content": BODY, "truncated": False})
        return httpx.Response(
            200,
            json={
                "id": 1296269,
                "default_branch": "master",
                "private": False,
                "description": BODY,
            },
            headers=headers,
        )


def _run(github: FakeGitHub, args: argparse.Namespace) -> github_smoke.Smoke:
    with httpx.Client(transport=httpx.MockTransport(github)) as client:
        smoke = github_smoke.Smoke(client, f"Basic {SECRET}")
        github_smoke.run(smoke, args)
    return smoke


def test_smoke_reads_only_and_prints_no_bodies():
    github = FakeGitHub()
    args = argparse.Namespace(
        repo=("octocat", "Hello-World"),
        renamed=("twitter", "bootstrap"),
        user="octocat",
        org="github",
        empty_repo=("octocat", "empty"),
    )

    smoke = _run(github, args)

    assert github.requests
    for request in github.requests:
        assert request.method == "GET"
        assert (request.url.scheme, request.url.host) == ("https", "api.github.com")
    printed = " ".join(
        f"{r.label} {r.status} {r.rate} {r.location} {r.conclusion}" for r in smoke.rows
    )
    assert BODY not in printed
    assert SECRET not in printed
    conclusions = {r.label: r.conclusion for r in smoke.rows}
    assert conclusions["rate_limit"].endswith("app credentials accepted")
    assert conclusions["renamed repository"] == "redirect to repository id 2126244"
    assert conclusions["empty repository contributors"] == "204 as documented"


@pytest.mark.parametrize(
    ("spends_304", "verdict"),
    [(False, "used 1 -> 1 -> 2: 304 is free"), (True, "used 1 -> 2 -> 3: 304 spends the limit")],
)
def test_smoke_compares_the_304_with_the_request_just_before(spends_304, verdict):
    smoke = _run(FakeGitHub(spends_304), _args())

    labels = [row.label for row in smoke.rows]
    conditional = labels.index("same, If-None-Match")
    assert labels[conditional - 1] == "repository by name"
    assert smoke.rows[conditional].conclusion == verdict


def test_smoke_needs_credentials_in_the_environment(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_CLIENT_ID", raising=False)
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", SECRET)
    monkeypatch.setattr("sys.argv", ["github_smoke.py"])

    assert github_smoke.main() == 2
    assert SECRET not in capsys.readouterr().out


@pytest.mark.parametrize("value", ["octocat", "octocat/", "../x/y", "a/b/c", "octo cat/x"])
def test_smoke_rejects_malformed_repository_names(value):
    with pytest.raises(argparse.ArgumentTypeError):
        github_smoke._full_name(value)


def _args() -> argparse.Namespace:
    return argparse.Namespace(
        repo=("octocat", "Hello-World"),
        renamed=("twitter", "bootstrap"),
        user="octocat",
        org="github",
        empty_repo=None,
    )


@pytest.mark.parametrize("resources", [None, [], {"core": None}, {"core": [1]}])
def test_smoke_survives_an_odd_rate_limit_body(resources):
    github = FakeGitHub()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/rate_limit":
            return httpx.Response(200, json={"resources": resources})
        return github(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        smoke = github_smoke.Smoke(client, "Basic x")
        github_smoke.run(smoke, _args())

    assert smoke.rows[0].conclusion == "core limit None: NOT the app limit"
    assert len(smoke.rows) > 5


def test_smoke_prints_collected_rows_when_it_stops(monkeypatch, capsys):
    def failing_run(smoke, args):
        smoke.rows.append(github_smoke.Row("rate_limit", "200", "-", "-", "ok"))
        raise RuntimeError(SECRET)

    monkeypatch.setenv("GITHUB_CLIENT_ID", "id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", SECRET)
    monkeypatch.setattr("sys.argv", ["github_smoke.py"])
    monkeypatch.setattr(github_smoke, "run", failing_run)

    assert github_smoke.main() == 0
    out = capsys.readouterr().out
    assert "rate_limit" in out
    assert "script stopped  RuntimeError" in out
    assert SECRET not in out
