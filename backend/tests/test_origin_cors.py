"""Origin check on state-changing requests and CORS headers."""

import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from app.dependencies import get_current_user
from app.main import app, frontend_origin
from app.origin_check import _normalize, origin_of
from tests.conftest import HTTPS_BASE_URL, login

PROFILE = "/api/v1/profile"
FOREIGN = "https://evil.example"
PREFLIGHT = {
    "Access-Control-Request-Method": "PATCH",
    "Access-Control-Request-Headers": "content-type",
}


def _assert_origin_rejected(resp) -> None:
    assert resp.status_code == 403
    error = resp.json()["error"]
    assert error["code"] == "CSRF_ORIGIN_INVALID"
    assert error["request_id"] == resp.headers["x-request-id"]


@pytest.fixture
def no_origin_client(make_auth_client):
    client = make_auth_client(send_origin=False)
    login(client)  # GET requests: not subject to the Origin check
    return client


class TestOriginCheck:
    @pytest.mark.parametrize(
        ("method", "path", "kwargs"),
        [
            ("patch", PROFILE, {"json": {"display_name": "X"}}),
            ("post", "/api/v1/profile/publish", {}),
            ("post", "/api/v1/profile/unpublish", {}),
            ("post", "/api/v1/auth/logout", {}),
        ],
    )
    def test_missing_origin_rejected(self, no_origin_client, method, path, kwargs):
        _assert_origin_rejected(getattr(no_origin_client, method)(path, **kwargs))

    @pytest.mark.parametrize(
        "origin",
        [
            FOREIGN,
            "null",
            "http://localhost:3001",
            "https://localhost:3000",
            "http://localhost.evil.example:3000",
            "http://localhost:3000/path",
            "http://user@localhost:3000",
            "not a url",
        ],
    )
    def test_foreign_origin_rejected(self, no_origin_client, origin):
        resp = no_origin_client.patch(
            PROFILE, json={"display_name": "X"}, headers={"Origin": origin}
        )
        _assert_origin_rejected(resp)

    def test_rejected_request_changes_nothing(self, no_origin_client):
        no_origin_client.patch(PROFILE, json={"display_name": "Evil"}, headers={"Origin": FOREIGN})
        assert no_origin_client.get(PROFILE).json()["display_name"] is None

    def test_logout_without_origin_keeps_session(self, no_origin_client):
        _assert_origin_rejected(no_origin_client.post("/api/v1/auth/logout"))
        assert no_origin_client.get("/api/v1/auth/me").status_code == 200

    @pytest.mark.parametrize("origin", [frontend_origin, frontend_origin.upper()])
    def test_correct_origin_passes(self, no_origin_client, origin):
        resp = no_origin_client.patch(
            PROFILE, json={"display_name": "Ann"}, headers={"Origin": origin}
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Ann"

    def test_get_is_not_checked(self, no_origin_client):
        assert no_origin_client.get(PROFILE).status_code == 200
        assert no_origin_client.get(PROFILE, headers={"Origin": FOREIGN}).status_code == 200


class TestOriginNormalization:
    def test_origin_of_drops_trailing_slash_and_default_port(self):
        assert origin_of(HttpUrl("http://localhost:3000")) == "http://localhost:3000"
        assert origin_of(HttpUrl("https://App.Example.com/")) == "https://app.example.com"
        assert origin_of(HttpUrl("https://app.example.com:443/x")) == "https://app.example.com"
        assert origin_of(HttpUrl("http://app.example.com:8080")) == "http://app.example.com:8080"

    def test_default_port_and_case_are_normalized(self):
        expected = ("https", "app.example.com", 443)
        assert _normalize("https://app.example.com") == expected
        assert _normalize("https://APP.example.com:443") == expected
        assert _normalize("HTTPS://app.example.com") == expected

    @pytest.mark.parametrize(
        "value", ["null", "", "ftp://app.example.com", "https://app.example.com/", "http://h:99999"]
    )
    def test_invalid_origins_do_not_normalize(self, value):
        assert _normalize(value) is None


class TestCors:
    def test_preflight_from_frontend_allowed(self):
        resp = TestClient(app).options(PROFILE, headers={"Origin": frontend_origin, **PREFLIGHT})
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == frontend_origin
        assert resp.headers["access-control-allow-credentials"] == "true"
        assert "PATCH" in resp.headers["access-control-allow-methods"]
        assert "content-type" in resp.headers["access-control-allow-headers"].lower()

    def test_preflight_from_foreign_origin_refused(self):
        resp = TestClient(app).options(PROFILE, headers={"Origin": FOREIGN, **PREFLIGHT})
        assert resp.status_code == 400
        assert "access-control-allow-origin" not in resp.headers

    def test_401_has_cors_headers_and_request_id(self):
        resp = TestClient(app).get(PROFILE, headers={"Origin": frontend_origin})
        assert resp.status_code == 401
        assert resp.headers["access-control-allow-origin"] == frontend_origin
        assert resp.headers["access-control-allow-credentials"] == "true"
        assert resp.headers["access-control-expose-headers"] == "X-Request-ID"
        assert resp.json()["error"]["request_id"] == resp.headers["x-request-id"]

    @pytest.mark.parametrize("headers", [{}, {"Origin": FOREIGN}], ids=["no-origin", "foreign"])
    def test_403_passes_through_cors_without_granting_access(self, headers):
        resp = TestClient(app, base_url=HTTPS_BASE_URL).post("/api/v1/auth/logout", headers=headers)
        _assert_origin_rejected(resp)
        assert "Origin" in resp.headers["vary"]
        assert "access-control-allow-origin" not in resp.headers

    def test_500_is_produced_inside_cors(self):
        def boom():
            raise RuntimeError("internal detail")

        app.dependency_overrides[get_current_user] = boom
        try:
            # raise_server_exceptions stays on: the exception must not reach the server layer.
            resp = TestClient(app).get(PROFILE, headers={"Origin": frontend_origin})
        finally:
            app.dependency_overrides.pop(get_current_user)

        assert resp.status_code == 500
        error = resp.json()["error"]
        assert set(error) == {"code", "message", "details", "request_id"}
        assert error["code"] == "INTERNAL_ERROR"
        assert error["request_id"] == resp.headers["x-request-id"]
        assert resp.headers["access-control-allow-origin"] == frontend_origin
        assert resp.headers["access-control-allow-credentials"] == "true"
        assert "internal detail" not in resp.text
