import os
from collections.abc import Callable, Generator
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pytest
from alembic import command as alembic_command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Set required env vars before any app module is imported during test collection.
# DATABASE_URL has no default in settings; this satisfies the validator without
# connecting to a real database (the health endpoint does not use the DB).
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://test:test@localhost:5432/developer_platform_test",
)
os.environ.setdefault("GITHUB_CLIENT_ID", "test_client_id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test_client_secret")
os.environ.setdefault(
    "GITHUB_CALLBACK_URL",
    "http://localhost:8000/api/v1/auth/github/callback",
)
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")

_BACKEND_DIR = Path(__file__).parent.parent

# Cookies are Secure outside development; the cookie jar sends them only over https.
HTTPS_BASE_URL = "https://testserver"


def _is_test_database_url(url: str) -> bool:
    """Returns True only if the database name in the URL contains 'test'."""
    if not url.startswith("postgresql"):
        return False
    try:
        db_name = urlparse(url).path.lstrip("/")
        return "test" in db_name
    except Exception:
        return False


def _postgres_available(url: str) -> bool:
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def db_engine():
    """
    Session-scoped engine for database tests.

    Runs alembic upgrade head once per test session against the PostgreSQL
    instance named in DATABASE_URL. Skips if the URL does not point to a
    test database (name must contain 'test') or if PostgreSQL is not reachable,
    so tests that do not depend on this fixture (e.g. the health endpoint test)
    still pass.
    """
    url = os.environ.get("DATABASE_URL", "")

    if not _is_test_database_url(url):
        pytest.skip("refusing to run against a non-test database")

    if not _postgres_available(url):
        pytest.skip(
            "PostgreSQL not reachable — set DATABASE_URL to a running "
            "PostgreSQL instance to run database constraint tests"
        )

    alembic_cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    alembic_command.upgrade(alembic_cfg, "head")

    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """
    Function-scoped session providing per-test transaction isolation.

    Each test runs inside a transaction rolled back at teardown. The session
    uses join_transaction_mode="create_savepoint" so that the session's own
    begin/commit cycle operates via SAVEPOINTs — the outer transaction is
    never committed and is always rolled back cleanly, even after an
    IntegrityError that aborts the inner SAVEPOINT.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


class _MockTransport(httpx.BaseTransport):
    """Minimal synchronous mock transport for httpx.Client."""

    def __init__(self, handler):
        self._handler = handler

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self._handler(request)


GitHubResponder = Callable[[httpx.Request], httpx.Response]


def make_github_transport(
    *,
    access_token: str = "gha_test_token",
    github_user_id: int = 10001,
    github_login: str = "testuser",
    email: str | None = "test@example.com",
    avatar_url: str | None = "https://avatars.githubusercontent.com/u/10001?v=4",
    code_error: str | None = None,
    token_response: GitHubResponder | None = None,
    user_response: GitHubResponder | None = None,
) -> _MockTransport:
    """
    Returns a synchronous mock transport that handles GitHub OAuth and user API calls.

    Pass code_error to simulate GitHub returning an error body on code exchange (e.g.
    'bad_verification_code'). token_response / user_response replace the default
    responses entirely; they may also raise httpx exceptions (e.g. ReadTimeout).
    avatar_url=None omits the field from the user response.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "login/oauth/access_token" in url:
            if token_response is not None:
                return token_response(request)
            if code_error:
                return httpx.Response(200, json={"error": code_error})
            return httpx.Response(200, json={"access_token": access_token})
        if "api.github.com/user" in url:
            if user_response is not None:
                return user_response(request)
            user = {"id": github_user_id, "login": github_login, "email": email}
            if avatar_url is not None:
                user["avatar_url"] = avatar_url
            return httpx.Response(200, json=user)
        return httpx.Response(404, json={"message": "Not Found"})

    return _MockTransport(handler)


@pytest.fixture
def make_auth_client(db_session: Session) -> Generator[Callable[..., TestClient]]:
    """
    Factory for TestClients with get_db and get_github_client overridden.

    The GitHub override is global to the app, so the transport passed to the most
    recent call is used by every client created in the test.
    """
    from app.dependencies import get_db
    from app.identity.github_client import GitHubOAuthClient, get_github_client
    from app.main import app, frontend_origin

    clients: list[TestClient] = []

    def override_db() -> Generator[Session]:
        yield db_session

    def make(
        transport: _MockTransport | None = None,
        *,
        send_origin: bool = True,
        **client_kwargs,
    ) -> TestClient:
        # State-changing requests must carry the frontend Origin, as a browser would.
        if send_origin:
            client_kwargs.setdefault("headers", {"Origin": frontend_origin})
        mock_client = GitHubOAuthClient(
            httpx.Client(transport=transport or make_github_transport())
        )

        def override_github() -> Generator[GitHubOAuthClient]:
            yield mock_client

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_github_client] = override_github
        client = TestClient(
            app, base_url=HTTPS_BASE_URL, follow_redirects=False, **client_kwargs
        )
        clients.append(client)
        return client

    yield make

    for client in clients:
        client.close()
    app.dependency_overrides.clear()


def login(client: TestClient) -> str:
    """Run the OAuth flow against the mocked GitHub; returns the session token."""
    from app.settings import settings

    state = client.get("/api/v1/auth/github/login").cookies["oauth_state"]
    resp = client.get(f"/api/v1/auth/github/callback?code=c&state={state}")
    assert resp.status_code == 302, resp.text
    return resp.cookies[settings.session_cookie_name]


@pytest.fixture
def auth_client(make_auth_client) -> TestClient:
    """TestClient with the default GitHub mock (user id=10001, login='testuser')."""
    return make_auth_client()
