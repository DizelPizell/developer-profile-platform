"""Security properties of the login flow: sessions, cookies and GitHub error paths."""

import hashlib
from datetime import UTC, datetime, timedelta
from http.cookies import Morsel, SimpleCookie

import httpx
import pytest
from sqlalchemy import select

import app.models  # noqa: F401 — registers all tables on Base.metadata
from app.database import Base
from app.identity import service
from app.models.identity import AuthSession
from app.settings import settings
from tests.conftest import make_github_transport

LOGIN = "/api/v1/auth/github/login"
CALLBACK = "/api/v1/auth/github/callback"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"
STATE_COOKIE_PATH = "/api/v1/auth/github"


def _set_cookies(resp: httpx.Response) -> dict[str, Morsel]:
    cookies: dict[str, Morsel] = {}
    for header in resp.headers.get_list("set-cookie"):
        parsed = SimpleCookie()
        parsed.load(header)
        cookies.update(parsed)
    return cookies


def _start_login(client) -> str:
    return client.get(LOGIN).cookies["oauth_state"]


def _login(client) -> str:
    state = _start_login(client)
    resp = client.get(f"{CALLBACK}?code=good_code&state={state}")
    assert resp.status_code == 302
    return resp.cookies[settings.session_cookie_name]


def _session_row(db_session, token: str) -> AuthSession | None:
    return db_session.execute(
        select(AuthSession).where(AuthSession.token_hash == service.hash_token(token))
    ).scalar_one_or_none()


def _assert_error(resp: httpx.Response, status: int, code: str) -> None:
    assert resp.status_code == status
    assert resp.json()["error"]["code"] == code


FRONTEND_LOGIN = f"{str(settings.frontend_url).rstrip('/')}/login"


def _assert_login_error(resp: httpx.Response, code: str) -> None:
    assert resp.status_code == 302
    assert resp.headers["location"] == f"{FRONTEND_LOGIN}?error={code}"


def _timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timed out", request=request)


def _status(code: int, **kwargs):
    return lambda request: httpx.Response(code, **kwargs)


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


class TestLogoutInvalidation:
    def test_old_token_rejected_after_logout(self, auth_client, db_session):
        token = _login(auth_client)
        assert auth_client.get(ME).status_code == 200

        assert auth_client.post(LOGOUT).status_code == 204

        # Re-send the old token explicitly: the server must reject it, not just the jar.
        auth_client.cookies.set(settings.session_cookie_name, token)
        _assert_error(auth_client.get(ME), 401, "UNAUTHORIZED")
        assert _session_row(db_session, token) is None


# ---------------------------------------------------------------------------
# Cookie attributes
# ---------------------------------------------------------------------------


class TestCookieAttributes:
    def test_state_cookie_attributes(self, auth_client):
        cookie = _set_cookies(auth_client.get(LOGIN))["oauth_state"]
        assert cookie["httponly"] is True
        assert cookie["samesite"].lower() == "lax"
        assert cookie["path"] == STATE_COOKIE_PATH
        assert cookie["max-age"] == "600"

    def test_session_cookie_attributes(self, auth_client):
        state = _start_login(auth_client)
        resp = auth_client.get(f"{CALLBACK}?code=c&state={state}")
        cookie = _set_cookies(resp)[settings.session_cookie_name]
        assert cookie["httponly"] is True
        assert cookie["samesite"].lower() == "lax"
        assert cookie["path"] == "/"
        assert cookie["max-age"] == str(settings.session_ttl_days * 86400)

    @pytest.mark.parametrize(("app_env", "secure"), [("production", True), ("development", False)])
    def test_secure_flag_depends_on_app_env(self, auth_client, monkeypatch, app_env, secure):
        monkeypatch.setattr(settings, "app_env", app_env)

        login = auth_client.get(LOGIN)
        state = login.cookies["oauth_state"]
        callback = auth_client.get(f"{CALLBACK}?code=c&state={state}")
        logout = auth_client.post(LOGOUT)

        set_by_login = _set_cookies(login)["oauth_state"]
        set_by_callback = _set_cookies(callback)
        set_by_logout = _set_cookies(logout)[settings.session_cookie_name]
        for cookie in (
            set_by_login,
            set_by_callback["oauth_state"],
            set_by_callback[settings.session_cookie_name],
            set_by_logout,
        ):
            assert bool(cookie["secure"]) is secure

    def test_state_cookie_deleted_with_same_attributes(self, auth_client):
        state = _start_login(auth_client)
        deleted = _set_cookies(auth_client.get(f"{CALLBACK}?code=c&state={state}"))["oauth_state"]
        assert deleted["max-age"] == "0"
        assert deleted["path"] == STATE_COOKIE_PATH
        assert deleted["httponly"] is True
        assert deleted["samesite"].lower() == "lax"
        assert bool(deleted["secure"]) is settings.secure_cookies

    def test_session_cookie_deleted_with_same_attributes(self, auth_client):
        _login(auth_client)
        deleted = _set_cookies(auth_client.post(LOGOUT))[settings.session_cookie_name]
        assert deleted["max-age"] == "0"
        assert deleted["path"] == "/"
        assert deleted["httponly"] is True
        assert deleted["samesite"].lower() == "lax"
        assert bool(deleted["secure"]) is settings.secure_cookies


# ---------------------------------------------------------------------------
# Callback error paths
# ---------------------------------------------------------------------------


class TestCallbackErrors:
    def test_missing_code(self, auth_client):
        state = _start_login(auth_client)
        _assert_login_error(auth_client.get(f"{CALLBACK}?state={state}"), "MISSING_CODE")

    def test_state_in_query_without_cookie(self, auth_client):
        _assert_login_error(auth_client.get(f"{CALLBACK}?code=c&state=anything"), "INVALID_STATE")

    def test_cookie_without_state_in_query(self, auth_client):
        _start_login(auth_client)
        _assert_login_error(auth_client.get(f"{CALLBACK}?code=c"), "INVALID_STATE")

    @pytest.mark.parametrize(
        "transport_kwargs",
        [
            pytest.param({"token_response": _timeout}, id="exchange-timeout"),
            pytest.param({"token_response": _status(503)}, id="exchange-5xx"),
            pytest.param({"user_response": _timeout}, id="user-timeout"),
            pytest.param({"user_response": _status(500)}, id="user-5xx"),
            pytest.param(
                {"token_response": _status(200, json={"token_type": "bearer"})},
                id="exchange-without-access-token",
            ),
            pytest.param(
                {"token_response": _status(200, text="not json")}, id="exchange-not-json"
            ),
            pytest.param({"token_response": _status(200, json=["x"])}, id="exchange-not-dict"),
            pytest.param(
                {"user_response": _status(200, json={"login": "u"})}, id="user-without-id"
            ),
            pytest.param(
                {"user_response": _status(200, json={"id": 1})}, id="user-without-login"
            ),
            pytest.param({"user_response": _status(200, text="<html>")}, id="user-not-json"),
            pytest.param({"user_response": _status(200, json=[1])}, id="user-not-dict"),
        ],
    )
    def test_github_failures_redirect_to_login(self, make_auth_client, transport_kwargs):
        client = make_auth_client(make_github_transport(**transport_kwargs))
        state = _start_login(client)
        resp = client.get(f"{CALLBACK}?code=c&state={state}")

        _assert_login_error(resp, "GITHUB_UNAVAILABLE")
        cookies = _set_cookies(resp)
        assert settings.session_cookie_name not in cookies
        assert cookies["oauth_state"]["max-age"] == "0"

    def test_state_cookie_deleted_on_error(self, auth_client):
        _start_login(auth_client)
        resp = auth_client.get(f"{CALLBACK}?code=c&state=wrong")
        _assert_login_error(resp, "INVALID_STATE")
        assert _set_cookies(resp)["oauth_state"]["max-age"] == "0"

    def test_unexpected_error_redirects_and_deletes_state_cookie(
        self, auth_client, monkeypatch
    ):
        def boom(*args, **kwargs):
            raise RuntimeError("internal detail")

        monkeypatch.setattr(service, "create_session", boom)
        state = _start_login(auth_client)
        resp = auth_client.get(f"{CALLBACK}?code=c&state={state}")

        _assert_login_error(resp, "INTERNAL_ERROR")
        assert "internal detail" not in resp.text
        cookies = _set_cookies(resp)
        assert cookies["oauth_state"]["max-age"] == "0"
        assert settings.session_cookie_name not in cookies


# ---------------------------------------------------------------------------
# Session token storage
# ---------------------------------------------------------------------------


class TestSessionStorage:
    def test_db_stores_sha256_of_cookie_token(self, auth_client, db_session):
        token = _login(auth_client)
        row = _session_row(db_session, token)
        assert row is not None
        assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert row.token_hash != token
        raw = db_session.execute(
            select(AuthSession).where(AuthSession.token_hash == token)
        ).scalar_one_or_none()
        assert raw is None

    def test_github_token_never_in_response_or_db(self, make_auth_client, db_session):
        github_token = "gho_UNIQUE_GITHUB_TOKEN_42"
        client = make_auth_client(make_github_transport(access_token=github_token))

        state = _start_login(client)
        callback = client.get(f"{CALLBACK}?code=c&state={state}")
        me = client.get(ME)
        assert callback.status_code == 302 and me.status_code == 200

        for resp in (callback, me):
            assert github_token not in resp.text
            assert all(github_token not in value for value in resp.headers.values())

        db_session.flush()
        for table in Base.metadata.sorted_tables:
            rows = db_session.execute(select(table)).all()
            assert github_token not in repr(rows), table.name

    def test_two_logins_issue_different_tokens(self, auth_client, db_session):
        first = _login(auth_client)
        auth_client.cookies.clear()
        second = _login(auth_client)

        assert first != second
        # Without the old cookie the first session is left untouched.
        assert _session_row(db_session, first) is not None
        assert _session_row(db_session, second) is not None

    def test_relogin_with_valid_cookie_deletes_old_session(self, auth_client, db_session):
        old = _login(auth_client)
        new = _login(auth_client)  # jar sends the old session cookie to the callback

        assert old != new
        assert _session_row(db_session, old) is None
        assert _session_row(db_session, new) is not None


# ---------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------


class TestMeResponse:
    def test_exact_response_keys(self, auth_client):
        _login(auth_client)
        body = auth_client.get(ME).json()
        assert set(body) == {"id", "github_login", "email", "profile_slug"}

    def test_expired_session_returns_401(self, auth_client, db_session):
        token = _login(auth_client)
        row = _session_row(db_session, token)
        assert row is not None
        row.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        db_session.flush()

        _assert_error(auth_client.get(ME), 401, "UNAUTHORIZED")
