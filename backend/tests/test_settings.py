import pytest
from pydantic import ValidationError

from app.settings import Settings

_VALID = {
    "app_env": "test",
    "database_url": "postgresql+psycopg://u:p@localhost:5432/developer_platform_test",
    "github_client_id": "id",
    "github_client_secret": "secret",
    "github_callback_url": "http://localhost:8000/api/v1/auth/github/callback",
    "frontend_url": "http://localhost:3000",
}


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **{**_VALID, **overrides})


def test_valid_settings_load():
    s = _settings()
    assert s.app_env == "test"


def test_app_env_is_required(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    values = {k: v for k, v in _VALID.items() if k != "app_env"}
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_app_env_rejects_unknown_value():
    with pytest.raises(ValidationError):
        _settings(app_env="staging")


@pytest.mark.parametrize("field", ["github_client_id", "github_client_secret"])
def test_empty_github_credentials_rejected(field):
    with pytest.raises(ValidationError):
        _settings(**{field: ""})


@pytest.mark.parametrize("field", ["github_callback_url", "frontend_url"])
def test_invalid_url_rejected(field):
    with pytest.raises(ValidationError):
        _settings(**{field: "not-a-url"})


@pytest.mark.parametrize("ttl", [0, -1])
def test_session_ttl_must_be_positive(ttl):
    with pytest.raises(ValidationError):
        _settings(session_ttl_days=ttl)


def test_client_secret_hidden_in_repr():
    s = _settings(github_client_secret="super-secret-value")
    assert "super-secret-value" not in repr(s)
    assert s.github_client_secret.get_secret_value() == "super-secret-value"


@pytest.mark.parametrize(
    ("app_env", "expected"),
    [("development", False), ("test", True), ("production", True)],
)
def test_secure_cookies_off_only_in_development(app_env, expected):
    assert _settings(app_env=app_env).secure_cookies is expected
