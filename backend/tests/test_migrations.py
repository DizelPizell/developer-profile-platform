"""All migrations apply to an empty database and roll back cleanly."""

import os
import uuid
from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.settings import settings

_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"


def test_migrations_apply_to_empty_database(db_engine, monkeypatch):
    # db_engine provides the "test database only / reachable" guards.
    base_url = make_url(os.environ["DATABASE_URL"])
    temp_name = f"{base_url.database}_migrations_{uuid.uuid4().hex[:8]}"
    temp_url = base_url.set(database=temp_name).render_as_string(hide_password=False)

    admin = create_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{temp_name}"'))
    try:
        # alembic/env.py takes the URL from settings, not from the Config object.
        monkeypatch.setattr(settings, "database_url", temp_url)
        cfg = Config(str(_ALEMBIC_INI))

        alembic_command.upgrade(cfg, "head")
        engine = create_engine(temp_url)
        try:
            schema = inspect(engine)
            assert {"users", "auth_sessions", "github_accounts", "profiles"} <= set(
                schema.get_table_names()
            )
            profile_columns = {c["name"] for c in schema.get_columns("profiles")}
            assert {"display_name", "headline", "bio", "location"} <= profile_columns
            assert "avatar_url" in {c["name"] for c in schema.get_columns("github_accounts")}
            checks = {c["name"] for c in schema.get_check_constraints("profiles")}
            assert {
                "ck_profiles_display_name",
                "ck_profiles_headline",
                "ck_profiles_bio",
                "ck_profiles_location",
                "ck_profiles_published_complete",
            } <= checks

            alembic_command.downgrade(cfg, "base")
            assert set(inspect(engine).get_table_names()) == {"alembic_version"}

            alembic_command.upgrade(cfg, "head")
            assert "profiles" in inspect(engine).get_table_names()
        finally:
            engine.dispose()
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{temp_name}" WITH (FORCE)'))
        admin.dispose()
