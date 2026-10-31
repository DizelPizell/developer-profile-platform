"""Sync jobs queued by link and import (ADR-018, step 6.2): one job per request in
the link's transaction, an active job reused, the link's metadata read recorded as
a metadata success, and nothing written when the link fails."""

from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.github import service as github_service
from app.models.github import GitHubRepository, GitHubSyncCategoryStatus, GitHubSyncJob
from tests.test_github_constraints import _repository
from tests.test_github_link_api import (
    LOGIN,
    OTHER_GITHUB_ID,
    STRANGER,
    STRANGER_ID,
    T0,
    Env,
    _create,
    _error,
    _link,
    _other_user,
    _repo,
    _timeout,
    make_env,
)

REPOSITORIES = "/api/v1/integrations/github/repositories"


@pytest.fixture
def env(make_auth_client, db_session: Session) -> Env:
    return make_env(make_auth_client, db_session)


def _import(http: TestClient, repository_id: int) -> httpx.Response:
    return http.post(f"{REPOSITORIES}/{repository_id}/import")


def _jobs(db: Session, github_repo_id: int) -> list[tuple]:
    return list(
        db.execute(
            select(
                GitHubSyncJob.status,
                GitHubSyncJob.attempt_count,
                GitHubSyncJob.scheduled_at,
                GitHubSyncJob.created_at,
                GitHubSyncJob.updated_at,
            )
            .join(GitHubRepository, GitHubRepository.id == GitHubSyncJob.github_repository_id)
            .where(GitHubRepository.github_repo_id == github_repo_id)
            .order_by(GitHubSyncJob.created_at)
        )
    )


def _categories(db: Session, github_repo_id: int) -> list[tuple]:
    return list(
        db.execute(
            select(
                GitHubSyncCategoryStatus.category,
                GitHubSyncCategoryStatus.last_success_at,
                GitHubSyncCategoryStatus.last_error,
                GitHubSyncCategoryStatus.last_error_at,
            )
            .join(
                GitHubRepository,
                GitHubRepository.id == GitHubSyncCategoryStatus.github_repository_id,
            )
            .where(GitHubRepository.github_repo_id == github_repo_id)
            .order_by(GitHubSyncCategoryStatus.category)
        )
    )


def _set_job_status(db: Session, github_repo_id: int, status: str) -> None:
    repository_id = db.scalar(
        select(GitHubRepository.id).where(GitHubRepository.github_repo_id == github_repo_id)
    )
    db.execute(
        GitHubSyncJob.__table__.update()
        .where(GitHubSyncJob.github_repository_id == repository_id)
        .values(status=status)
    )
    db.commit()


# enqueue_sync.


def test_enqueue_creates_a_queued_job_with_the_given_times(db_session):
    repository = _repository(db_session)
    now = datetime(2026, 10, 31, 9, 30)

    job_id, created = github_service.enqueue_sync(db_session, repository.id, now)

    job = db_session.get(GitHubSyncJob, job_id)
    assert created is True
    assert (job.status, job.attempt_count, job.last_error) == ("QUEUED", 0, None)
    assert (job.scheduled_at, job.created_at, job.updated_at) == (now, now, now)


@pytest.mark.parametrize("status", ["QUEUED", "SYNCING"])
def test_enqueue_returns_the_active_job(db_session, status):
    repository = _repository(db_session)
    job_id, _ = github_service.enqueue_sync(db_session, repository.id, T0)
    db_session.get(GitHubSyncJob, job_id).status = status
    db_session.flush()

    again, created = github_service.enqueue_sync(db_session, repository.id, T0 + timedelta(hours=1))

    assert (again, created) == (job_id, False)
    assert db_session.get(GitHubSyncJob, job_id).created_at == T0


@pytest.mark.parametrize("status", ["SYNCED", "FAILED"])
def test_enqueue_after_a_finished_job_creates_a_new_one(db_session, status):
    repository = _repository(db_session)
    first, _ = github_service.enqueue_sync(db_session, repository.id, T0)
    db_session.get(GitHubSyncJob, first).status = status
    db_session.flush()

    second, created = github_service.enqueue_sync(db_session, repository.id, T0 + timedelta(days=1))

    assert created is True
    assert second != first


# Link and import.


def test_link_queues_a_job_and_records_the_metadata_read(env, db_session):
    env.github.add(_repo(1))

    resp = _link(env.http, _create(env.http), f"{LOGIN}/repo-1")

    assert resp.status_code == 200, resp.text
    assert _jobs(db_session, 1) == [("QUEUED", 0, T0, T0, T0)]
    assert _categories(db_session, 1) == [("metadata", T0, None, None)]


def test_import_queues_a_job_and_records_the_metadata_read(env, db_session):
    env.github.add(_repo(1))

    resp = _import(env.http, 1)

    assert resp.status_code == 201, resp.text
    assert _jobs(db_session, 1) == [("QUEUED", 0, T0, T0, T0)]
    assert _categories(db_session, 1) == [("metadata", T0, None, None)]


def test_another_link_reuses_the_active_job(env, make_auth_client, db_session):
    env.github.add(_repo(1), contributors=[[OTHER_GITHUB_ID]])
    other, _ = _other_user(make_auth_client, db_session)
    project_id = _create(env.http)
    _link(env.http, project_id, f"{LOGIN}/repo-1")
    env.clock.now = T0 + timedelta(minutes=1)

    # Another user's project and the same project again: the job stays one.
    assert _link(other, _create(other), f"{LOGIN}/repo-1").status_code == 200
    assert _link(env.http, project_id, f"{LOGIN}/repo-1").status_code == 200

    assert _jobs(db_session, 1) == [("QUEUED", 0, T0, T0, T0)]
    later = T0 + timedelta(minutes=1)
    assert _categories(db_session, 1) == [("metadata", later, None, None)]


def test_link_after_a_finished_job_queues_a_new_one(env, db_session):
    env.github.add(_repo(1))
    project_id = _create(env.http)
    _link(env.http, project_id, f"{LOGIN}/repo-1")
    _set_job_status(db_session, 1, "SYNCED")
    env.clock.now = later = T0 + timedelta(minutes=1)

    _link(env.http, project_id, f"{LOGIN}/repo-1")

    assert _jobs(db_session, 1) == [
        ("SYNCED", 0, T0, T0, T0),
        ("QUEUED", 0, later, later, later),
    ]


def test_link_clears_a_metadata_error(env, db_session):
    """A 404 before the link and one after it are not two in a row (ADR-018)."""
    env.github.add(_repo(1))
    project_id = _create(env.http)
    _link(env.http, project_id, f"{LOGIN}/repo-1")
    db_session.execute(
        GitHubSyncCategoryStatus.__table__.update().values(
            last_error="NOT_FOUND", last_error_at=T0 + timedelta(minutes=1)
        )
    )
    db_session.commit()
    env.clock.now = later = T0 + timedelta(minutes=2)

    _link(env.http, project_id, f"{LOGIN}/repo-1")

    assert _categories(db_session, 1) == [("metadata", later, None, None)]


def test_refused_link_queues_nothing(env, db_session):
    env.github.add(_repo(3, owner=STRANGER, owner_id=STRANGER_ID), contributors=[[1]])

    resp = _link(env.http, _create(env.http), f"{STRANGER}/repo-3")

    _error(resp, 422, "GITHUB_RELATION_NOT_FOUND")
    assert _jobs(db_session, 3) == []
    assert _categories(db_session, 3) == []


def test_github_failure_queues_nothing(env, db_session):
    env.github.respond = _timeout

    resp = _link(env.http, _create(env.http), f"{LOGIN}/repo-1")

    _error(resp, 502, "GITHUB_UNAVAILABLE")
    assert _jobs(db_session, 1) == []
    assert _categories(db_session, 1) == []


def test_conflicting_link_leaves_the_job_and_metadata_as_they_were(env, db_session):
    env.github.add(_repo(1))
    _link(env.http, _create(env.http), f"{LOGIN}/repo-1")
    _set_job_status(db_session, 1, "SYNCED")
    env.clock.now = T0 + timedelta(minutes=1)

    resp = _link(env.http, _create(env.http), f"{LOGIN}/repo-1")

    _error(resp, 409, "GITHUB_REPOSITORY_ALREADY_LINKED")
    assert _jobs(db_session, 1) == [("SYNCED", 0, T0, T0, T0)]
    assert _categories(db_session, 1) == [("metadata", T0, None, None)]


def test_conflicting_import_queues_nothing(env, db_session):
    env.github.add(_repo(1))
    assert _import(env.http, 1).status_code == 201
    _set_job_status(db_session, 1, "FAILED")
    env.clock.now = T0 + timedelta(minutes=1)

    resp = _import(env.http, 1)

    _error(resp, 409, "GITHUB_REPOSITORY_ALREADY_LINKED")
    assert _jobs(db_session, 1) == [("FAILED", 0, T0, T0, T0)]
