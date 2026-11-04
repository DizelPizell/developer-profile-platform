"""Periodic syncs (ADR-018, step 6.5): which repositories get a job, how many at
a time, and that the enqueue stays idempotent."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Event

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.github import worker as worker_module
from app.github.worker import enqueue_periodic_syncs
from app.models.github import GitHubRepository, GitHubSyncJob
from app.models.identity import User
from app.models.projects import Project
from app.settings import settings
from tests.conftest import wait_until_blocked
from tests.test_github_constraints import _link, _owner, _repository, _repository_fields
from tests.test_github_worker import (
    Clock,
    Recorder,
    _seen,
    _session_that_does_not_wait,
    _worker,
)

T0 = datetime(2026, 11, 1, 12, 0)
DAY = timedelta(days=1)


def _project(db: Session, status: str = "PUBLISHED", visibility: str = "PUBLIC") -> Project:
    fields = {}
    if status == "PUBLISHED":
        fields = {"title": "T", "summary": "S", "role": "R", "contribution": "C"}
    project = Project(owner_id=_owner(db).id, status=status, visibility=visibility, **fields)
    db.add(project)
    db.flush()
    return project


def _linked(db: Session, status: str = "PUBLISHED", visibility: str = "PUBLIC", **fields):
    repository = _repository(db, **fields)
    _link(db, _project(db, status, visibility), repository)
    db.commit()
    return repository


def _job(db: Session, repository: GitHubRepository, created_at: datetime, status: str) -> None:
    db.add(
        GitHubSyncJob(
            github_repository_id=repository.id,
            status=status,
            scheduled_at=created_at,
            created_at=created_at,
            updated_at=created_at,
        )
    )
    db.commit()


def _jobs(db: Session, repository: GitHubRepository) -> list[GitHubSyncJob]:
    return list(
        db.scalars(
            select(GitHubSyncJob)
            .where(GitHubSyncJob.github_repository_id == repository.id)
            .order_by(GitHubSyncJob.created_at)
        )
    )


# ---------------------------------------------------------------------------
# Which repositories
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("visibility", ["PUBLIC", "PRIVATE"])
def test_a_repository_of_a_published_project_is_queued(db_session, visibility):
    repository = _linked(db_session, visibility=visibility)

    assert enqueue_periodic_syncs(db_session, T0) == 1

    (job,) = _jobs(db_session, repository)
    assert (job.status, job.attempt_count, job.last_error) == ("QUEUED", 0, None)
    assert (job.scheduled_at, job.created_at, job.updated_at) == (T0, T0, T0)


@pytest.mark.parametrize("status", ["DRAFT", "ARCHIVED"])
def test_a_repository_of_an_unpublished_project_is_not_queued(db_session, status):
    repository = _linked(db_session, status, "PRIVATE")

    assert enqueue_periodic_syncs(db_session, T0) == 0
    assert _jobs(db_session, repository) == []


def test_a_repository_without_links_is_not_queued(db_session):
    repository = _repository(db_session)

    assert enqueue_periodic_syncs(db_session, T0) == 0
    assert _jobs(db_session, repository) == []


def test_one_published_project_among_several_is_enough_and_gives_one_job(db_session):
    repository = _linked(db_session, "DRAFT", "PRIVATE")
    _link(db_session, _project(db_session), repository)
    _link(db_session, _project(db_session), repository)
    db_session.commit()

    assert enqueue_periodic_syncs(db_session, T0) == 1
    assert len(_jobs(db_session, repository)) == 1


def test_an_unavailable_repository_is_queued(db_session):
    repository = _linked(db_session, unavailable_since=T0 - DAY)

    assert enqueue_periodic_syncs(db_session, T0) == 1
    assert len(_jobs(db_session, repository)) == 1


# ---------------------------------------------------------------------------
# The period
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["SYNCED", "FAILED"])
def test_a_job_within_the_period_holds_the_next_one(db_session, status):
    repository = _linked(db_session)
    _job(db_session, repository, T0 - DAY + timedelta(seconds=1), status)

    assert enqueue_periodic_syncs(db_session, T0) == 0


@pytest.mark.parametrize("status", ["SYNCED", "FAILED"])
def test_a_job_exactly_a_period_old_is_due(db_session, status):
    repository = _linked(db_session)
    _job(db_session, repository, T0 - DAY, status)

    assert enqueue_periodic_syncs(db_session, T0) == 1
    assert [job.created_at for job in _jobs(db_session, repository)] == [T0 - DAY, T0]


def test_the_latest_of_several_jobs_decides(db_session):
    repository = _linked(db_session)
    _job(db_session, repository, T0 - 3 * DAY, "SYNCED")
    _job(db_session, repository, T0 - timedelta(hours=1), "FAILED")

    assert enqueue_periodic_syncs(db_session, T0) == 0


def test_the_period_is_configurable(db_session, monkeypatch):
    monkeypatch.setattr(settings, "github_periodic_sync_seconds", 60)
    repository = _linked(db_session)
    _job(db_session, repository, T0 - timedelta(seconds=60), "SYNCED")

    assert enqueue_periodic_syncs(db_session, T0) == 1


def test_a_second_call_queues_nothing(db_session):
    _linked(db_session)

    assert enqueue_periodic_syncs(db_session, T0) == 1
    assert enqueue_periodic_syncs(db_session, T0) == 0


# ---------------------------------------------------------------------------
# The batch
# ---------------------------------------------------------------------------


def test_a_batch_is_limited_and_the_next_call_takes_the_rest(db_session, monkeypatch):
    monkeypatch.setattr(settings, "github_periodic_sync_batch", 2)
    for _ in range(5):
        _linked(db_session)

    assert [enqueue_periodic_syncs(db_session, T0) for _ in range(4)] == [2, 2, 1, 0]


@pytest.mark.parametrize("status", ["QUEUED", "SYNCING"])
def test_an_old_active_job_takes_no_place_in_the_batch(db_session, monkeypatch, status):
    monkeypatch.setattr(settings, "github_periodic_sync_batch", 1)
    for repository in [_linked(db_session) for _ in range(3)]:
        _job(db_session, repository, T0 - 3 * DAY, status)
    due = _linked(db_session)

    assert enqueue_periodic_syncs(db_session, T0) == 1
    assert len(_jobs(db_session, due)) == 1


# ---------------------------------------------------------------------------
# In the worker's iteration
# ---------------------------------------------------------------------------


def test_a_job_queued_by_an_iteration_is_run_by_it(db_session):
    repository = _linked(db_session)
    recorder = Recorder()

    assert _worker(recorder).run_once(db_session) is True

    assert [job.github_repository_id for job in recorder.jobs] == [repository.id]
    assert _jobs(db_session, repository)[0].status == "SYNCED"


def test_the_enqueue_runs_at_most_once_a_minute(db_session):
    clock = Clock()
    worker = _worker(Recorder(), clock)
    worker.run_once(db_session)
    repository = _linked(db_session)

    clock.now = T0 + timedelta(seconds=59)
    assert worker.run_once(db_session) is False
    assert _jobs(db_session, repository) == []

    clock.now = T0 + timedelta(seconds=60)
    assert worker.run_once(db_session) is True
    assert len(_jobs(db_session, repository)) == 1


def test_nothing_is_queued_during_a_rate_limit_pause(db_session):
    clock = Clock()
    repository = _linked(db_session)
    worker = _worker(Recorder(), clock)
    worker.client.pause.start(T0 + timedelta(minutes=10))

    assert worker.run_once(db_session) is False
    assert _jobs(db_session, repository) == []

    clock.now = T0 + timedelta(minutes=10)
    assert worker.run_once(db_session) is True
    assert len(_jobs(db_session, repository)) == 1


def test_nothing_is_queued_within_the_reserve(db_session):
    clock = Clock()
    repository = _linked(db_session)
    worker = _worker(Recorder(), clock)
    reset_at = T0 + timedelta(minutes=10)
    _seen(worker, settings.github_worker_reserve, reset_at)

    assert worker.run_once(db_session) is False
    assert _jobs(db_session, repository) == []

    clock.now = reset_at
    assert worker.run_once(db_session) is True
    assert len(_jobs(db_session, repository)) == 1


def test_an_enqueue_that_fails_does_not_stop_the_claims(db_session, monkeypatch):
    def broken(db: Session, now: datetime) -> int:
        raise RuntimeError("the enqueue failed")

    repository = _repository(db_session)
    _job(db_session, repository, T0, "QUEUED")
    monkeypatch.setattr(worker_module, "enqueue_periodic_syncs", broken)
    recorder = Recorder()
    worker = _worker(recorder)

    with pytest.raises(RuntimeError):
        worker.run_once(db_session)
    assert recorder.jobs == []

    assert worker.run_once(db_session) is True
    assert len(recorder.jobs) == 1


# ---------------------------------------------------------------------------
# Two transactions
# ---------------------------------------------------------------------------


class TestConcurrentEnqueue:
    @pytest.fixture
    def repository_id(self, db_engine):
        with Session(db_engine) as db:
            github_repo_id = 800_000 + uuid.uuid4().int % 100_000
            repository = GitHubRepository(**_repository_fields(github_repo_id=github_repo_id))
            db.add(repository)
            db.flush()
            project = _project(db)
            _link(db, project, repository)
            owner_id = project.owner_id
            repository_id = repository.id
            db.commit()
        yield repository_id
        with Session(db_engine) as db:
            db.execute(delete(User).where(User.id == owner_id))
            db.execute(delete(GitHubRepository).where(GitHubRepository.id == repository_id))
            db.commit()

    def test_an_uncommitted_job_of_another_transaction_is_not_doubled(
        self, db_engine, repository_id
    ):
        """The selection cannot see the other job, so the partial unique index
        decides: the insert waits for it and then does nothing."""
        pids: list[int] = []
        connected = Event()

        def enqueue() -> int:
            with _session_that_does_not_wait(db_engine) as db:
                pids.append(db.scalar(text("SELECT pg_backend_pid()")))
                connected.set()
                return enqueue_periodic_syncs(db, T0)

        with Session(db_engine) as holder, ThreadPoolExecutor(1) as pool:
            holder.add(GitHubSyncJob(github_repository_id=repository_id, scheduled_at=T0))
            holder.flush()
            queued = pool.submit(enqueue)
            assert connected.wait(timeout=5)
            wait_until_blocked(db_engine, pids[0])
            holder.commit()

            assert queued.result(timeout=5) == 0

        with Session(db_engine) as db:
            count = select(func.count()).select_from(GitHubSyncJob)
            assert db.scalar(count.where(GitHubSyncJob.github_repository_id == repository_id)) == 1
