import os
from pathlib import Path

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


def _postgres_available(url: str) -> bool:
    if not url.startswith("postgresql"):
        return False
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
    instance named in DATABASE_URL. Skips the entire session with a clear
    message if PostgreSQL is not reachable, so tests that do not depend on
    this fixture (e.g. the health endpoint test) still pass.
    """
    url = os.environ.get("DATABASE_URL", "")
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

    Each test runs inside a database transaction that is rolled back at
    teardown — the dev database is never touched. Rollback works even after
    an IntegrityError because PostgreSQL accepts ROLLBACK on aborted
    transactions.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        # After an IntegrityError, SQLAlchemy aborts the transaction internally
        # and deassociates it from the connection. is_active guards the rollback.
        if transaction.is_active:
            transaction.rollback()
        connection.close()
