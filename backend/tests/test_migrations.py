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

            # ADR-009, ADR-018: sync jobs and category freshness.
            assert {"github_sync_jobs", "github_sync_category_status"} <= set(
                schema.get_table_names()
            )
            assert {
                "ck_github_sync_jobs_status",
                "ck_github_sync_jobs_attempt_count",
                "ck_github_sync_jobs_last_error",
            } <= {c["name"] for c in schema.get_check_constraints("github_sync_jobs")}
            assert {
                "ck_github_sync_category_status_category",
                "ck_github_sync_category_status_last_error",
                "ck_github_sync_category_status_error_time",
            } <= {c["name"] for c in schema.get_check_constraints("github_sync_category_status")}
            with engine.connect() as conn:
                job_indexes = dict(
                    conn.execute(
                        text(
                            "SELECT indexname, indexdef FROM pg_indexes "
                            "WHERE tablename = 'github_sync_jobs'"
                        )
                    ).all()
                )
            assert "UNIQUE" in job_indexes["uq_github_sync_jobs_active"]
            assert "'QUEUED'" in job_indexes["uq_github_sync_jobs_active"]
            assert "'SYNCING'" in job_indexes["uq_github_sync_jobs_active"]
            assert "WHERE" in job_indexes["ix_github_sync_jobs_claim"]
            assert "ix_github_sync_jobs_repository_created" in job_indexes

            alembic_command.downgrade(cfg, "818c44e09940")
            tables = set(inspect(engine).get_table_names())
            assert not {"github_sync_jobs", "github_sync_category_status"} & tables
            assert {"github_repositories", "project_repositories"} <= tables

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


def test_sync_tables_keep_existing_links(db_engine, monkeypatch):
    """Links made before the sync tables survive the upgrade and the downgrade,
    and have no jobs: their status is NOT_SYNCED (ADR-018)."""
    base_url = make_url(os.environ["DATABASE_URL"])
    temp_name = f"{base_url.database}_migrations_{uuid.uuid4().hex[:8]}"
    temp_url = base_url.set(database=temp_name).render_as_string(hide_password=False)

    admin = create_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{temp_name}"'))
    try:
        monkeypatch.setattr(settings, "database_url", temp_url)
        cfg = Config(str(_ALEMBIC_INI))
        alembic_command.upgrade(cfg, "818c44e09940")
        engine = create_engine(temp_url)
        try:
            with engine.begin() as conn:
                user_id = conn.execute(
                    text(
                        "INSERT INTO users (github_user_id, github_login) "
                        "VALUES (7001, 'ann') RETURNING id"
                    )
                ).scalar_one()
                project_id = conn.execute(
                    text("INSERT INTO projects (owner_id) VALUES (:user) RETURNING id"),
                    {"user": user_id},
                ).scalar_one()
                repository_id = conn.execute(
                    text(
                        "INSERT INTO github_repositories (github_repo_id, owner_github_id, "
                        "owner_login, name, full_name, html_url, is_fork, is_archived) "
                        "VALUES (42, 7001, 'ann', 'site', 'ann/site', "
                        "'https://github.com/ann/site', false, false) RETURNING id"
                    )
                ).scalar_one()
                conn.execute(
                    text(
                        "INSERT INTO project_repositories "
                        "(project_id, owner_id, github_repository_id, relation) "
                        "VALUES (:project, :user, :repository, 'OWNER')"
                    ),
                    {"project": project_id, "user": user_id, "repository": repository_id},
                )

            def link() -> tuple:
                with engine.connect() as conn:
                    return conn.execute(
                        text(
                            "SELECT r.full_name, l.relation FROM project_repositories l "
                            "JOIN github_repositories r ON r.id = l.github_repository_id "
                            "WHERE l.project_id = :project"
                        ),
                        {"project": project_id},
                    ).one()

            alembic_command.upgrade(cfg, "head")
            assert link() == ("ann/site", "OWNER")
            with engine.connect() as conn:
                assert conn.execute(text("SELECT count(*) FROM github_sync_jobs")).scalar_one() == 0
                assert (
                    conn.execute(
                        text("SELECT count(*) FROM github_sync_category_status")
                    ).scalar_one()
                    == 0
                )

            alembic_command.downgrade(cfg, "818c44e09940")
            assert link() == ("ann/site", "OWNER")
        finally:
            engine.dispose()
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{temp_name}" WITH (FORCE)'))
        admin.dispose()
