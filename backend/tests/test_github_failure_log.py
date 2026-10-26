"""The reason for GITHUB_UNAVAILABLE is logged, without secrets or response bodies."""

import logging

import httpx
import pytest

from app.settings import settings
from tests.conftest import make_github_transport

CALLBACK = "/api/v1/auth/github/callback"
CODE = "SECRET_OAUTH_CODE_123"
GITHUB_TOKEN = "gho_SECRET_ACCESS_TOKEN"
BODY_MARKER = "SECRET_RESPONSE_BODY"


def _timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timed out", request=request)


@pytest.fixture
def error_log(caplog, monkeypatch):
    # alembic's fileConfig (db_engine fixture) disables loggers that existed before it ran.
    monkeypatch.setattr(logging.getLogger("app.errors"), "disabled", False)
    caplog.set_level(logging.WARNING, logger="app.errors")
    return caplog


@pytest.mark.parametrize(
    ("transport_kwargs", "reason", "github_status"),
    [
        ({"token_response": _timeout}, "ReadTimeout", "None"),
        (
            {"token_response": lambda r: httpx.Response(503, text=BODY_MARKER)},
            "HTTPStatusError",
            "503",
        ),
        (
            {"user_response": lambda r: httpx.Response(500, json={"message": BODY_MARKER})},
            "HTTPStatusError",
            "500",
        ),
        (
            {"token_response": lambda r: httpx.Response(200, json={"note": BODY_MARKER})},
            "missing_access_token",
            "200",
        ),
        (
            {"user_response": lambda r: httpx.Response(200, text=f"<html>{BODY_MARKER}")},
            "JSONDecodeError",
            "200",
        ),
    ],
    ids=["timeout", "exchange-5xx", "user-5xx", "no-access-token", "user-not-json"],
)
def test_reason_logged_without_secrets(
    make_auth_client, error_log, transport_kwargs, reason, github_status
):
    client = make_auth_client(make_github_transport(access_token=GITHUB_TOKEN, **transport_kwargs))
    state = client.get("/api/v1/auth/github/login").cookies["oauth_state"]
    resp = client.get(f"{CALLBACK}?code={CODE}&state={state}")

    assert resp.status_code == 302
    request_id = resp.headers["x-request-id"]

    records = [r for r in error_log.records if r.name == "app.errors"]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    message = record.getMessage()
    assert "GITHUB_UNAVAILABLE" in message
    assert f"request_id={request_id}" in message
    assert f"reason={reason}" in message
    assert f"github_status={github_status}" in message

    for secret in (
        CODE,
        state,
        GITHUB_TOKEN,
        BODY_MARKER,
        settings.github_client_secret.get_secret_value(),
        "?code=",
        "https://",
    ):
        assert secret not in error_log.text
