"""Database sessions run in UTC, whatever the server's default time zone."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text

# Nine hours from UTC, so a session in it cannot pass for UTC.
_OTHER_TIME_ZONE = "Asia/Tokyo"


@pytest.fixture
def non_utc_database_default(db_engine):
    """New connections to the test database default to another time zone.

    The CI image already defaults to UTC, so without this the tests would pass
    even if the application did not set the time zone itself.
    """
    admin = db_engine.execution_options(isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        name = conn.execute(text("SELECT current_database()")).scalar_one()
        conn.execute(text(f"ALTER DATABASE \"{name}\" SET timezone = '{_OTHER_TIME_ZONE}'"))
    try:
        yield
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'ALTER DATABASE "{name}" RESET timezone'))


def test_a_connection_without_the_setting_follows_the_database_default(
    db_engine, non_utc_database_default
):
    plain = create_engine(db_engine.url)
    try:
        with plain.connect() as conn:
            assert conn.execute(text("SHOW timezone")).scalar_one() == _OTHER_TIME_ZONE
    finally:
        plain.dispose()


def test_application_session_runs_in_utc(non_utc_database_default):
    from app.database import SessionLocal, engine

    # Pooled connections were opened before the default changed.
    engine.dispose()
    with SessionLocal() as session:
        assert session.execute(text("SHOW timezone")).scalar_one() == "UTC"
        # now() of server defaults matches the naive UTC the application writes.
        server_now = session.execute(text("SELECT localtimestamp")).scalar_one()
    assert abs(server_now - datetime.now(UTC).replace(tzinfo=None)) < timedelta(minutes=1)


def test_test_session_runs_in_utc(db_engine, non_utc_database_default):
    db_engine.dispose()
    with db_engine.connect() as conn:
        assert conn.execute(text("SHOW timezone")).scalar_one() == "UTC"
