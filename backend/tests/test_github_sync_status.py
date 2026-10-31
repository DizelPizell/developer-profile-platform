"""github.sync and synced_at in the cabinet project response (ADR-018, step 6.2):
the latest job's status, the time of the older category's success, and when a
manual sync is allowed again."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session

from app.models.github import GitHubRepository, GitHubSyncCategoryStatus, GitHubSyncJob
from app.settings import settings
from tests.test_github_link_api import LOGIN, PROJECTS, T0, Env, _create, _link, _repo, make_env


@pytest.fixture
def env(make_auth_client, db_session: Session) -> Env:
    return make_env(make_auth_client, db_session)


def _linked(env: Env) -> str:
    env.github.add(_repo(1))
    project_id = _create(env.http)
    assert _link(env.http, project_id, f"{LOGIN}/repo-1").status_code == 200
    return project_id


def _github(env: Env, project_id: str) -> dict:
    resp = env.http.get(f"{PROJECTS}/{project_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()["github"]


def _repository_id(db: Session):
    return db.scalar(select(GitHubRepository.id).where(GitHubRepository.github_repo_id == 1))


def _replace_jobs(db: Session, *jobs: tuple[str, datetime]) -> None:
    repository_id = _repository_id(db)
    db.execute(delete(GitHubSyncJob).where(GitHubSyncJob.github_repository_id == repository_id))
    for status, created_at in jobs:
        db.add(
            GitHubSyncJob(
                github_repository_id=repository_id,
                status=status,
                scheduled_at=created_at,
                created_at=created_at,
                updated_at=created_at,
            )
        )
    db.commit()


def _set_success(db: Session, category: str, at: datetime | None) -> None:
    repository_id = _repository_id(db)
    db.execute(
        delete(GitHubSyncCategoryStatus).where(
            GitHubSyncCategoryStatus.github_repository_id == repository_id,
            GitHubSyncCategoryStatus.category == category,
        )
    )
    db.add(
        GitHubSyncCategoryStatus(
            github_repository_id=repository_id, category=category, last_success_at=at
        )
    )
    db.commit()


def _iso(value: datetime) -> str:
    return value.isoformat() + "Z"


def test_a_link_without_jobs_is_not_synced(env, db_session):
    """As links made before step 6.1 are."""
    project_id = _linked(env)
    _replace_jobs(db_session)

    assert _github(env, project_id)["sync"] == {
        "status": "NOT_SYNCED",
        "last_success_at": None,
        "next_manual_sync_at": None,
    }


@pytest.mark.parametrize("status", ["QUEUED", "SYNCING", "SYNCED", "FAILED"])
def test_status_is_the_latest_jobs(env, db_session, status):
    project_id = _linked(env)
    other = "FAILED" if status == "SYNCED" else "SYNCED"
    _replace_jobs(db_session, (other, T0 - timedelta(days=2)), (status, T0 - timedelta(days=1)))

    assert _github(env, project_id)["sync"]["status"] == status


def test_next_manual_sync_is_ten_minutes_after_the_latest_job(env, db_session):
    project_id = _linked(env)
    _replace_jobs(db_session, ("SYNCED", T0 - timedelta(days=1)), ("FAILED", T0))

    env.clock.now = T0 + timedelta(minutes=9, seconds=59)
    assert _github(env, project_id)["sync"]["next_manual_sync_at"] == "2026-10-30T12:10:00Z"

    env.clock.now = T0 + timedelta(minutes=10)
    assert _github(env, project_id)["sync"]["next_manual_sync_at"] is None


def test_next_manual_sync_shows_while_a_job_is_active(env):
    project_id = _linked(env)

    sync = _github(env, project_id)["sync"]

    assert (sync["status"], sync["next_manual_sync_at"]) == ("QUEUED", "2026-10-30T12:10:00Z")


def test_the_pause_is_configurable(env, monkeypatch):
    monkeypatch.setattr(settings, "github_manual_sync_cooldown_seconds", 60)
    project_id = _linked(env)

    assert _github(env, project_id)["sync"]["next_manual_sync_at"] == "2026-10-30T12:01:00Z"


def test_a_link_alone_is_not_a_successful_sync(env):
    """The link records the metadata read, but languages wait for a sync."""
    project_id = _linked(env)

    github = _github(env, project_id)

    assert (github["synced_at"], github["sync"]["last_success_at"]) == (None, None)
    assert github["languages"] == []


@pytest.mark.parametrize(
    ("metadata", "languages", "expected"),
    [
        (T0 - timedelta(hours=1), T0 - timedelta(hours=3), T0 - timedelta(hours=3)),
        (T0 - timedelta(hours=3), T0 - timedelta(hours=1), T0 - timedelta(hours=3)),
        (T0 - timedelta(hours=1), None, None),
        (None, T0 - timedelta(hours=1), None),
    ],
)
def test_data_is_as_old_as_its_oldest_category(env, db_session, metadata, languages, expected):
    project_id = _linked(env)
    _set_success(db_session, "metadata", metadata)
    _set_success(db_session, "languages", languages)

    github = _github(env, project_id)

    expected = _iso(expected) if expected else None
    assert (github["synced_at"], github["sync"]["last_success_at"]) == (expected, expected)


def test_the_number_of_queries_does_not_grow_with_jobs(env, db_session):
    project_id = _linked(env)

    def statements() -> int:
        seen: list[str] = []

        def count(conn, cursor, statement, *args) -> None:
            seen.append(statement)

        connection = db_session.connection()
        event.listen(connection, "before_cursor_execute", count)
        try:
            _github(env, project_id)
        finally:
            event.remove(connection, "before_cursor_execute", count)
        return len(seen)

    one = statements()
    _replace_jobs(db_session, *[("SYNCED", T0 - timedelta(days=day)) for day in range(30, 0, -1)])
    _set_success(db_session, "languages", T0)

    assert statements() == one
