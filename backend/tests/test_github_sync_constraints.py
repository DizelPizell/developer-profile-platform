"""
Database constraint tests for the GitHub sync tables (ADR-009, ADR-011, ADR-018).

Isolation strategy: each test runs inside a transaction that is rolled
back at teardown by the db_session fixture. The alembic migration is
applied once per session by db_engine. The dev database is never touched.
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models.github import GitHubSyncCategoryStatus, GitHubSyncJob
from tests.test_github_constraints import (
    _count,
    _flush_violates,
    _link,
    _owner,
    _project,
    _repository,
)

_NOW = datetime(2026, 10, 31, 12, 0)


def _job(db_session, repository, **fields) -> GitHubSyncJob:
    job = GitHubSyncJob(github_repository_id=repository.id, **fields)
    db_session.add(job)
    db_session.flush()
    return job


def _enqueue(db_session, repository) -> list:
    """The enqueue of ADR-018: an active job of the repository is kept."""
    return db_session.execute(
        text(
            "INSERT INTO github_sync_jobs (github_repository_id) VALUES (:repository) "
            "ON CONFLICT (github_repository_id) WHERE status IN ('QUEUED', 'SYNCING') "
            "DO NOTHING RETURNING id"
        ),
        {"repository": repository.id},
    ).all()


# ---------------------------------------------------------------------------
# github_sync_jobs
# ---------------------------------------------------------------------------


def test_job_defaults(db_session):
    job = _job(db_session, _repository(db_session))
    db_session.refresh(job)

    assert job.status == "QUEUED"
    assert job.attempt_count == 0
    assert job.last_error is None
    assert job.scheduled_at is not None
    assert job.created_at is not None
    assert job.updated_at is not None


@pytest.mark.parametrize("status", ["QUEUED", "SYNCING", "SYNCED", "FAILED"])
def test_job_accepts_each_status(db_session, status):
    job = _job(db_session, _repository(db_session), status=status)
    db_session.refresh(job)

    assert job.status == status


def test_job_accepts_an_error_label(db_session):
    job = _job(db_session, _repository(db_session), last_error="NOT_FOUND", attempt_count=2)
    db_session.refresh(job)

    assert (job.last_error, job.attempt_count) == ("NOT_FOUND", 2)


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"status": "queued"}, "ck_github_sync_jobs_status"),
        ({"status": "NOT_SYNCED"}, "ck_github_sync_jobs_status"),
        ({"status": "RETRYING"}, "ck_github_sync_jobs_status"),
        ({"attempt_count": -1}, "ck_github_sync_jobs_attempt_count"),
        ({"last_error": ""}, "ck_github_sync_jobs_last_error"),
        ({"last_error": "not_found"}, "ck_github_sync_jobs_last_error"),
        ({"last_error": "Bad credentials"}, "ck_github_sync_jobs_last_error"),
        ({"last_error": "HTTP_502"}, "ck_github_sync_jobs_last_error"),
        ({"last_error": "A" * 65}, "ck_github_sync_jobs_last_error"),
        ({"last_error": "NOT_FOUND\n"}, "ck_github_sync_jobs_last_error"),
    ],
)
def test_job_checks(db_session, fields, constraint):
    db_session.add(GitHubSyncJob(github_repository_id=_repository(db_session).id, **fields))

    _flush_violates(db_session, constraint)


@pytest.mark.parametrize(
    ("first", "second"),
    [("QUEUED", "QUEUED"), ("QUEUED", "SYNCING"), ("SYNCING", "QUEUED"), ("SYNCING", "SYNCING")],
)
def test_one_active_job_per_repository(db_session, first, second):
    repository = _repository(db_session)
    _job(db_session, repository, status=first)
    db_session.add(GitHubSyncJob(github_repository_id=repository.id, status=second))

    _flush_violates(db_session, "uq_github_sync_jobs_active")


def test_finished_jobs_do_not_block_a_new_job(db_session):
    repository = _repository(db_session)
    for status in ("SYNCED", "FAILED", "SYNCED", "FAILED"):
        _job(db_session, repository, status=status)
    _job(db_session, repository)

    assert (
        _count(
            db_session,
            "SELECT count(*) FROM github_sync_jobs WHERE github_repository_id = :id",
            id=repository.id,
        )
        == 5
    )


def test_active_jobs_of_different_repositories(db_session):
    first = _job(db_session, _repository(db_session))
    second = _job(db_session, _repository(db_session), status="SYNCING")

    assert first.id != second.id


def test_enqueue_reuses_the_active_job(db_session):
    repository = _repository(db_session)

    created = _enqueue(db_session, repository)
    assert len(created) == 1
    assert _enqueue(db_session, repository) == []

    job = db_session.get(GitHubSyncJob, created[0].id)
    job.status = "SYNCING"
    db_session.flush()
    assert _enqueue(db_session, repository) == []

    job.status = "SYNCED"
    db_session.flush()
    assert len(_enqueue(db_session, repository)) == 1


def test_job_needs_an_existing_repository(db_session):
    db_session.add(GitHubSyncJob(github_repository_id=uuid.uuid4()))

    _flush_violates(db_session, "github_sync_jobs_github_repository_id_fkey")


# ---------------------------------------------------------------------------
# github_sync_category_status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("category", ["metadata", "languages"])
def test_category_status_accepts_each_category(db_session, category):
    status = GitHubSyncCategoryStatus(
        github_repository_id=_repository(db_session).id,
        category=category,
        last_success_at=_NOW,
        last_error="NOT_FOUND",
        last_error_at=_NOW,
    )
    db_session.add(status)
    db_session.flush()
    db_session.refresh(status)

    assert (status.category, status.last_error) == (category, "NOT_FOUND")


def test_category_status_starts_empty(db_session):
    status = GitHubSyncCategoryStatus(
        github_repository_id=_repository(db_session).id, category="metadata"
    )
    db_session.add(status)
    db_session.flush()
    db_session.refresh(status)

    assert (status.last_success_at, status.last_error, status.last_error_at) == (None, None, None)


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"category": "readme"}, "ck_github_sync_category_status_category"),
        ({"category": "Metadata"}, "ck_github_sync_category_status_category"),
        ({"category": "contributors"}, "ck_github_sync_category_status_category"),
        (
            {"last_error": "not found", "last_error_at": _NOW},
            "ck_github_sync_category_status_last_error",
        ),
        ({"last_error": "NOT_FOUND"}, "ck_github_sync_category_status_error_time"),
        ({"last_error_at": _NOW}, "ck_github_sync_category_status_error_time"),
    ],
)
def test_category_status_checks(db_session, fields, constraint):
    db_session.add(
        GitHubSyncCategoryStatus(
            github_repository_id=_repository(db_session).id, **{"category": "metadata", **fields}
        )
    )

    _flush_violates(db_session, constraint)


def test_one_status_row_per_repository_and_category(db_session):
    repository = _repository(db_session)
    for category in ("metadata", "languages"):
        db_session.add(
            GitHubSyncCategoryStatus(github_repository_id=repository.id, category=category)
        )
    db_session.flush()
    db_session.add(
        GitHubSyncCategoryStatus(github_repository_id=repository.id, category="metadata")
    )

    _flush_violates(db_session, "uq_github_sync_category_status_repository_category")


# ---------------------------------------------------------------------------
# Deleting a repository
# ---------------------------------------------------------------------------


def test_deleting_an_unlinked_repository_removes_its_sync_records(db_session):
    """Raw SQL DELETE bypasses the ORM: checks the database-level cascade."""
    repository = _repository(db_session)
    other = _repository(db_session)
    for each in (repository, other):
        _job(db_session, each, status="SYNCED")
        _job(db_session, each)
        db_session.add(GitHubSyncCategoryStatus(github_repository_id=each.id, category="metadata"))
    db_session.flush()

    db_session.execute(
        text("DELETE FROM github_repositories WHERE id = :id"), {"id": repository.id}
    )

    remaining = db_session.scalars(select(GitHubSyncJob.github_repository_id)).all()
    assert repository.id not in remaining
    assert remaining.count(other.id) == 2
    assert not _count(
        db_session,
        "SELECT count(*) FROM github_sync_category_status WHERE github_repository_id = :id",
        id=repository.id,
    )
    assert _count(
        db_session,
        "SELECT count(*) FROM github_sync_category_status WHERE github_repository_id = :id",
        id=other.id,
    )


def test_a_linked_repository_with_jobs_cannot_be_deleted(db_session):
    repository = _repository(db_session)
    _link(db_session, _project(db_session, _owner(db_session)), repository)
    _job(db_session, repository)

    with pytest.raises(IntegrityError) as exc:
        db_session.execute(
            text("DELETE FROM github_repositories WHERE id = :id"), {"id": repository.id}
        )
    assert exc.value.orig.diag.constraint_name == "project_repositories_github_repository_id_fkey"
