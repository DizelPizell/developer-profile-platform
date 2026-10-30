"""The manual smoke script only reads api.github.com and prints no bodies or secrets."""

import argparse

import httpx
import pytest

from scripts import github_smoke

SECRET = "SMOKE_SECRET_MARKER"
BODY = "SMOKE_BODY_MARKER"


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    headers = {"x-ratelimit-limit": "5000", "x-ratelimit-remaining": "4990", "etag": '"abc"'}
    if path == "/rate_limit":
        return httpx.Response(200, json={"resources": {"core": {"limit": 5000}}, "x": BODY})
    if path == "/repos/twitter/bootstrap":
        return httpx.Response(
            301, headers={"location": "https://api.github.com/repositories/2126244"}
        )
    if request.headers.get("if-none-match"):
        return httpx.Response(304, headers=dict(headers, **{"x-ratelimit-used": "10"}))
    if path.endswith("/contributors") and "empty" in path:
        return httpx.Response(204)
    if path.startswith(("/users/", "/orgs/")) or path.endswith("/contributors"):
        return httpx.Response(200, json=[{"private": False, "description": BODY}])
    if path.endswith("/readme") or "/git/trees/" in path:
        return httpx.Response(200, json={"content": BODY, "truncated": False})
    return httpx.Response(
        200,
        json={"id": 1296269, "default_branch": "master", "private": False, "description": BODY},
        headers=dict(headers, **{"x-ratelimit-used": "10"}),
    )


def test_smoke_reads_only_and_prints_no_bodies():
    requests: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _handler(request)

    args = argparse.Namespace(
        repo=("octocat", "Hello-World"),
        renamed=("twitter", "bootstrap"),
        user="octocat",
        org="github",
        empty_repo=("octocat", "empty"),
    )
    with httpx.Client(transport=httpx.MockTransport(recording)) as client:
        smoke = github_smoke.Smoke(client, f"Basic {SECRET}")
        github_smoke.run(smoke, args)

    assert requests
    for request in requests:
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
    assert "304 looks free" in conclusions["same, If-None-Match"]


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
