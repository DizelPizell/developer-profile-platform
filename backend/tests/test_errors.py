"""Shared error format and request id."""

import uuid

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.errors import setup_error_handling
from app.main import app

ERROR_KEYS = {"code", "message", "details", "request_id"}


def _assert_error_shape(resp: httpx.Response, status: int, code: str) -> dict:
    assert resp.status_code == status
    error = resp.json()["error"]
    assert set(error) == ERROR_KEYS
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["details"], dict)
    assert error["request_id"] == resp.headers["x-request-id"]
    return error


@pytest.fixture
def client():
    return TestClient(app)


def test_404_uses_error_format(client):
    _assert_error_shape(client.get("/api/v1/does-not-exist"), 404, "NOT_FOUND")


def test_405_uses_error_format_and_keeps_allow_header(client):
    resp = client.get("/api/v1/auth/logout")
    _assert_error_shape(resp, 405, "METHOD_NOT_ALLOWED")
    assert "POST" in resp.headers["allow"]


def test_app_error_uses_error_format(client):
    _assert_error_shape(client.get("/api/v1/auth/me"), 401, "UNAUTHORIZED")


def test_500_uses_error_format_without_details():
    def boom():
        raise RuntimeError("internal detail")

    app.dependency_overrides[get_current_user] = boom
    try:
        resp = TestClient(app, raise_server_exceptions=False).get("/api/v1/auth/me")
    finally:
        app.dependency_overrides.pop(get_current_user)

    error = _assert_error_shape(resp, 500, "INTERNAL_ERROR")
    assert error["details"] == {}
    assert "internal detail" not in resp.text
    assert "RuntimeError" not in resp.text


def test_422_lists_fields_and_types_without_input_values():
    # No V1 endpoint can currently fail request validation, so use a minimal app
    # wired with the same error handling.
    validation_app = FastAPI()
    setup_error_handling(validation_app)

    @validation_app.get("/items/{item_id}")
    def get_item(item_id: int) -> dict:
        return {"item_id": item_id}

    resp = TestClient(validation_app).get("/items/SECRET_INPUT")

    error = _assert_error_shape(resp, 422, "VALIDATION_ERROR")
    assert error["details"] == {"fields": [{"loc": ["path", "item_id"], "type": "int_parsing"}]}
    assert "SECRET_INPUT" not in resp.text


def test_valid_incoming_request_id_is_reused(client):
    request_id = str(uuid.uuid4())
    resp = client.get("/api/v1/does-not-exist", headers={"X-Request-ID": request_id})
    assert resp.headers["x-request-id"] == request_id
    assert resp.json()["error"]["request_id"] == request_id


@pytest.mark.parametrize(
    "incoming",
    ["not-a-uuid", "", "123e4567e89b12d3a456426614174000", "x" * 500],
)
def test_invalid_incoming_request_id_is_replaced(client, incoming):
    resp = client.get("/api/v1/does-not-exist", headers={"X-Request-ID": incoming})
    returned = resp.headers["x-request-id"]
    assert returned != incoming
    assert str(uuid.UUID(returned)) == returned
    assert resp.json()["error"]["request_id"] == returned


def test_success_response_has_request_id(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert uuid.UUID(resp.headers["x-request-id"])
    assert len(resp.headers.get_list("x-request-id")) == 1
