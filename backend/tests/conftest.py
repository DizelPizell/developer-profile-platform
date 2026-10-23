import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Set required env vars before any app module is imported during test collection.
# DATABASE_URL has no default in settings; this satisfies the validator without
# connecting to a real database (the health endpoint does not use the DB).
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://test:test@localhost:5432/developer_platform_test",
)

_BACKEND_DIR = Path(__file__).parent.parent


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
