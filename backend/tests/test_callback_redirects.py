"""OAuth callback errors end with a redirect to the frontend sign-in screen."""

from http.cookies import SimpleCookie
from urllib.parse import quote

import httpx
import pytest
from sqlalchemy import func, select

from app.errors import AppError
from app.identity import service
from app.models.identity import AuthSession, User
from app.settings import settings
from tests.conftest import make_github_transport

LOGIN = "/api/v1/auth/github/login"
CALLBACK = "/api/v1/auth/github/callback"
FRONTEND_LOGIN = f"{str(settings.frontend_url).rstrip('/')}/login"

CODE = "callback-code-7f3a"
FORGED_STATE = "forged-state-91c2"
DESCRIPTION = "description-marker https://evil.example/?x=<script>"
EXCEPTION_TEXT = "internal-detail-5d0e"


def _start_login(client) -> str:
    return client.get(LOGIN).cookies["oauth_state"]


def _access_denied(make_auth_client, monkeypatch):
    client = make_auth_client()
    state = _start_login(client)
    query = f"error=access_denied&error_description={quote(DESCRIPTION)}&state={state}"
    return client.get(f"{CALLBACK}?{query}"), [state, DESCRIPTION]


def _invalid_state(make_auth_client, monkeypatch):
    client = make_auth_client()
    state = _start_login(client)
    return client.get(f"{CALLBACK}?code={CODE}&state={FORGED_STATE}"), [state, CODE, FORGED_STATE]


def _missing_code(make_auth_client, monkeypatch):
    client = make_auth_client()
    state = _start_login(client)
    return client.get(f"{CALLBACK}?state={state}"), [state]


def _oauth_code_invalid(make_auth_client, monkeypatch):
    client = make_auth_client(make_github_transport(code_error="bad_verification_code"))
    state = _start_login(client)
    resp = client.get(f"{CALLBACK}?code={CODE}&state={state}")
    return resp, [state, CODE, "bad_verification_code"]


def _github_unavailable(make_auth_client, monkeypatch):
    transport = make_github_transport(
        token_response=lambda request: httpx.Response(503, text=EXCEPTION_TEXT)
    )
    client = make_auth_client(transport)
    state = _start_login(client)
    return client.get(f"{CALLBACK}?code={CODE}&state={state}"), [state, CODE, EXCEPTION_TEXT]


def _unexpected_exception(make_auth_client, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError(EXCEPTION_TEXT)

    monkeypatch.setattr(service, "create_session", boom)
    client = make_auth_client()
    state = _start_login(client)
    return client.get(f"{CALLBACK}?code={CODE}&state={state}"), [state, CODE, EXCEPTION_TEXT]


def _code_outside_the_list(make_auth_client, monkeypatch):
    def slug_conflict(*args, **kwargs):
        raise AppError("SLUG_CONFLICT", EXCEPTION_TEXT, 500)

    monkeypatch.setattr(service, "create_session", slug_conflict)
    client = make_auth_client()
    state = _start_login(client)
    resp = client.get(f"{CALLBACK}?code={CODE}&state={state}")
    return resp, [state, CODE, EXCEPTION_TEXT, "SLUG_CONFLICT"]


CASES = [
    pytest.param(_access_denied, "ACCESS_DENIED", id="access-denied"),
    pytest.param(_invalid_state, "INVALID_STATE", id="invalid-state"),
    pytest.param(_missing_code, "MISSING_CODE", id="missing-code"),
    pytest.param(_oauth_code_invalid, "OAUTH_CODE_INVALID", id="oauth-code-invalid"),
    pytest.param(_github_unavailable, "GITHUB_UNAVAILABLE", id="github-unavailable"),
    pytest.param(_unexpected_exception, "INTERNAL_ERROR", id="unexpected-exception"),
    pytest.param(_code_outside_the_list, "INTERNAL_ERROR", id="code-outside-the-list"),
]


@pytest.mark.parametrize(("make_request", "code"), CASES)
class TestCallbackErrorRedirect:
    def test_redirects_to_frontend_login_with_code(
        self, make_auth_client, monkeypatch, make_request, code
    ):
        resp, _ = make_request(make_auth_client, monkeypatch)
        assert resp.status_code == 302
        assert resp.headers["location"] == f"{FRONTEND_LOGIN}?error={code}"
        assert resp.headers["x-request-id"]
        assert resp.content == b""

    def test_location_has_nothing_from_request_or_github(
        self, make_auth_client, monkeypatch, make_request, code
    ):
        resp, sensitive = make_request(make_auth_client, monkeypatch)
        location = resp.headers["location"]
        for value in [*sensitive, "state=", "code=", "error_description"]:
            assert value not in location
            assert quote(value) not in location

    def test_cookies_and_database_unchanged(
        self, make_auth_client, monkeypatch, db_session, make_request, code
    ):
        resp, _ = make_request(make_auth_client, monkeypatch)

        cookies = SimpleCookie()
        for header in resp.headers.get_list("set-cookie"):
            cookies.load(header)
        assert cookies["oauth_state"]["max-age"] == "0"
        assert settings.session_cookie_name not in cookies

        assert db_session.scalar(select(func.count()).select_from(User)) == 0
        assert db_session.scalar(select(func.count()).select_from(AuthSession)) == 0


def test_spoofed_error_value_still_gives_access_denied(make_auth_client):
    client = make_auth_client()
    resp = client.get(f"{CALLBACK}?error={quote(DESCRIPTION)}&error_description=x")
    assert resp.status_code == 302
    assert resp.headers["location"] == f"{FRONTEND_LOGIN}?error=ACCESS_DENIED"


def test_success_still_redirects_to_frontend_with_session(make_auth_client, db_session):
    client = make_auth_client()
    state = _start_login(client)
    resp = client.get(f"{CALLBACK}?code={CODE}&state={state}")

    assert resp.status_code == 302
    assert resp.headers["location"] == str(settings.frontend_url)
    assert settings.session_cookie_name in resp.cookies
    assert db_session.scalar(select(func.count()).select_from(AuthSession)) == 1
