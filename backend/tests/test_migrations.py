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

            assert {"projects", "technologies", "project_technologies", "project_showcases"} <= set(
                schema.get_table_names()
            )
            project_checks = {c["name"] for c in schema.get_check_constraints("projects")}
            assert {
                "ck_projects_state",
                "ck_projects_title",
                "ck_projects_summary",
                "ck_projects_description",
                "ck_projects_problem",
                "ck_projects_results",
                "ck_projects_role",
                "ck_projects_contribution",
                "ck_projects_published_complete",
            } <= project_checks
            technology_indexes = {i["name"]: i for i in schema.get_indexes("technologies")}
            assert technology_indexes["uq_technologies_name_lower"]["unique"]
            with engine.connect() as conn:
                deferrable = conn.execute(
                    text(
                        "SELECT condeferrable, condeferred FROM pg_constraint "
                        "WHERE conname = 'uq_project_showcases_position'"
                    )
                ).one()
            # DEFERRABLE INITIALLY IMMEDIATE (ADR-015).
            assert tuple(deferrable) == (True, False)

            # ADR-017: shared repositories and project links.
            assert {"github_repositories", "project_repositories"} <= set(schema.get_table_names())
            assert {
                "ck_github_repositories_names",
                "ck_github_repositories_full_name",
                "ck_github_repositories_html_url",
                "ck_github_repositories_languages",
            } <= {c["name"] for c in schema.get_check_constraints("github_repositories")}
            link_uniques = {
                u["name"] for u in schema.get_unique_constraints("project_repositories")
            }
            assert "uq_project_repositories_owner_repository" in link_uniques
            assert "uq_projects_id_owner" in {
                u["name"] for u in schema.get_unique_constraints("projects")
            }

            alembic_command.downgrade(cfg, "f09e0777cfe5")
            tables = set(inspect(engine).get_table_names())
            assert not {"github_repositories", "project_repositories"} & tables
            assert "uq_projects_id_owner" not in {
                u["name"] for u in inspect(engine).get_unique_constraints("projects")
            }

            alembic_command.downgrade(cfg, "a3f1c9e27b54")
            assert "projects" not in inspect(engine).get_table_names()
            assert "profiles" in inspect(engine).get_table_names()

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
