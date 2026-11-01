"""The GitHub sync worker (ADR-009, ADR-018, step 6.3): claims, outcomes,
retries, rate limits and the watchdog, with a processor given by the test.

Most tests run in db_session, where the worker's commits are savepoints. Tests
of two workers use their own sessions on db_engine, with committed rows they
delete at the end.
"""

import logging
import uuid
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.github import worker as worker_module
from app.github.client import (
    GitHubApiClient,
    GitHubCredentialsRejected,
    GitHubMoved,
    GitHubNotFound,
    GitHubRateLimited,
    GitHubUnavailable,
    GitHubUnexpected,
    RateLimit,
    RateLimitPause,
    RateLimitState,
)
from app.github.worker import (
    ClaimedJob,
    CredentialsError,
    SyncFailed,
    SyncWorker,
    check_credentials,
    claim_job,
    recover_stale_jobs,
    retry_delay,
)
from app.models.github import GitHubRepository, GitHubSyncJob
from app.settings import settings
from tests.test_github_constraints import _repository, _repository_fields

T0 = datetime(2026, 11, 1, 12, 0)
STALE = timedelta(minutes=10)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


def _no_network(request: httpx.Request) -> httpx.Response:
    raise AssertionError("the worker core makes no GitHub request")


def _worker(process, clock: Clock | None = None, handler=_no_network) -> SyncWorker:
    clock = clock or Clock()
    client = GitHubApiClient(
        httpx.Client(transport=httpx.MockTransport(handler)),
        "worker_client_id",
        "worker_client_secret",
        rate_limits=RateLimitState(),
        pause=RateLimitPause(),
        now=clock,
    )
    return SyncWorker(client, process, now=clock)


def _ok(db: Session, job: ClaimedJob) -> None:
    pass


def _raises(exc: BaseException):
    def process(db: Session, job: ClaimedJob) -> None:
        raise exc

    return process


class Recorder:
    def __init__(self, then=_ok) -> None:
        self.jobs: list[ClaimedJob] = []
        self.then = then

    def __call__(self, db: Session, job: ClaimedJob) -> None:
        self.jobs.append(job)
        self.then(db, job)


def _job(db: Session, repository: GitHubRepository | None = None, **fields) -> uuid.UUID:
    values = {
        "status": "QUEUED",
        "scheduled_at": T0,
        "created_at": T0 - timedelta(hours=1),
        "updated_at": T0 - timedelta(hours=1),
    }
    values.update(fields)
    job = GitHubSyncJob(github_repository_id=(repository or _repository(db)).id, **values)
    db.add(job)
    db.commit()
    return job.id


def _state(db: Session, job_id: uuid.UUID) -> dict:
    row = db.execute(
        select(
            GitHubSyncJob.status,
            GitHubSyncJob.attempt_count,
            GitHubSyncJob.scheduled_at,
            GitHubSyncJob.last_error,
            GitHubSyncJob.updated_at,
        ).where(GitHubSyncJob.id == job_id)
    ).one()
    return row._asdict()


@pytest.fixture
def worker_log(caplog, monkeypatch):
    # alembic's fileConfig (db_engine fixture) disables loggers that existed before it ran.
    monkeypatch.setattr(logging.getLogger(worker_module.__name__), "disabled", False)
    caplog.set_level(logging.INFO, logger=worker_module.__name__)
    return caplog


def _worker_records(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == worker_module.__name__]


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------


def test_runs_due_jobs_earliest_first(db_session):
    later = _job(db_session, scheduled_at=T0 - timedelta(minutes=1))
    earlier = _job(db_session, scheduled_at=T0 - timedelta(minutes=2))
    future = _job(db_session, scheduled_at=T0 + timedelta(seconds=1))
    process = Recorder()
    worker = _worker(process)

    assert [worker.run_once(db_session) for _ in range(3)] == [True, True, False]

    assert [job.id for job in process.jobs] == [earlier, later]
    assert _state(db_session, future)["status"] == "QUEUED"
    assert _state(db_session, future)["attempt_count"] == 0


def test_a_job_due_now_is_claimed(db_session):
    job_id = _job(db_session, scheduled_at=T0)

    assert _worker(_ok).run_once(db_session) is True
    assert _state(db_session, job_id)["status"] == "SYNCED"


def test_no_queued_job_runs_nothing(db_session):
    process = Recorder()

    assert _worker(process).run_once(db_session) is False
    assert process.jobs == []


@pytest.mark.parametrize("status", ["SYNCED", "FAILED", "SYNCING"])
def test_only_queued_jobs_are_claimed(db_session, status):
    job_id = _job(db_session, status=status, updated_at=T0)
    process = Recorder()

    assert _worker(process).run_once(db_session) is False
    assert process.jobs == []
    assert _state(db_session, job_id)["status"] == status


def test_the_job_is_syncing_with_its_attempt_counted_while_it_runs(db_session):
    repository = _repository(db_session)
    job_id = _job(db_session, repository, attempt_count=2)
    seen: list[dict] = []
    process = Recorder(lambda db, job: seen.append(_state(db, job.id)))

    _worker(process).run_once(db_session)

    assert process.jobs == [ClaimedJob(job_id, repository.id, 3)]
    assert seen[0]["status"] == "SYNCING"
    assert (seen[0]["attempt_count"], seen[0]["updated_at"]) == (3, T0)


# ---------------------------------------------------------------------------
# Outcomes and retries
# ---------------------------------------------------------------------------


def test_success_is_synced_and_clears_the_error(db_session):
    job_id = _job(db_session, attempt_count=1, last_error="WORKER_LOST")
    clock = Clock()

    def slow(db, job):
        clock.now = T0 + timedelta(seconds=30)

    _worker(slow, clock).run_once(db_session)

    state = _state(db_session, job_id)
    assert (state["status"], state["attempt_count"], state["last_error"]) == ("SYNCED", 2, None)
    assert state["updated_at"] == T0 + timedelta(seconds=30)


@pytest.mark.parametrize(
    ("exc", "label"),
    [
        (GitHubNotFound(), "NOT_FOUND"),
        (GitHubUnavailable("timeout"), "GITHUB_UNAVAILABLE"),
        (GitHubUnavailable("status_502", 502), "GITHUB_UNAVAILABLE"),
        (GitHubUnavailable("malformed_response", 200), "GITHUB_UNAVAILABLE"),
        (GitHubMoved(42), "UNEXPECTED_STATUS"),
        (GitHubUnexpected(418), "UNEXPECTED_STATUS"),
        (SyncFailed("NOT_FOUND"), "NOT_FOUND"),
        (RuntimeError("bug"), "INTERNAL_ERROR"),
    ],
)
def test_a_failure_is_retried_after_the_base_delay(db_session, exc, label):
    job_id = _job(db_session)

    assert _worker(_raises(exc)).run_once(db_session) is True

    assert _state(db_session, job_id) == {
        "status": "QUEUED",
        "attempt_count": 1,
        "scheduled_at": T0 + timedelta(seconds=30),
        "last_error": label,
        "updated_at": T0,
    }


@pytest.mark.parametrize(
    ("attempts_before", "delay"),
    [(0, 30), (1, 60), (2, 120), (3, 200), (5, 200)],
)
def test_the_retry_delay_doubles_up_to_the_maximum(db_session, monkeypatch, attempts_before, delay):
    monkeypatch.setattr(settings, "github_worker_retry_max_seconds", 200)
    monkeypatch.setattr(settings, "github_worker_max_attempts", 10)
    job_id = _job(db_session, attempt_count=attempts_before)

    _worker(_raises(GitHubUnavailable("timeout"))).run_once(db_session)

    assert _state(db_session, job_id)["scheduled_at"] == T0 + timedelta(seconds=delay)


def test_retry_delay_of_a_huge_attempt_is_the_maximum():
    assert retry_delay(10**6) == timedelta(seconds=1800)


def test_the_last_attempt_fails_the_job(db_session):
    job_id = _job(db_session, attempt_count=4)

    _worker(_raises(GitHubUnavailable("timeout"))).run_once(db_session)

    state = _state(db_session, job_id)
    assert (state["status"], state["attempt_count"]) == ("FAILED", 5)
    assert (state["last_error"], state["scheduled_at"]) == ("GITHUB_UNAVAILABLE", T0)


def test_the_attempt_limit_is_configurable(db_session, monkeypatch):
    monkeypatch.setattr(settings, "github_worker_max_attempts", 1)
    job_id = _job(db_session)

    _worker(_raises(GitHubNotFound())).run_once(db_session)

    assert _state(db_session, job_id)["status"] == "FAILED"


def test_a_final_failure_is_not_retried(db_session):
    job_id = _job(db_session)

    _worker(_raises(SyncFailed("NOT_FOUND", final=True))).run_once(db_session)

    state = _state(db_session, job_id)
    assert (state["status"], state["attempt_count"], state["last_error"]) == (
        "FAILED",
        1,
        "NOT_FOUND",
    )


@pytest.mark.parametrize("label", ["", "Not Found", "NOT_FOUND\n", "HTTP_404", "A" * 65])
def test_a_sync_failure_takes_only_a_label(label):
    with pytest.raises(ValueError):
        SyncFailed(label)


@pytest.mark.parametrize("outcome", [None, GitHubUnavailable("timeout")])
def test_what_the_processor_leaves_uncommitted_is_rolled_back(db_session, outcome):
    repository = _repository(db_session, description="before")
    db_session.commit()
    _job(db_session, repository)

    def process(db, job):
        db.execute(
            update(GitHubRepository)
            .where(GitHubRepository.id == repository.id)
            .values(description="uncommitted")
        )
        if outcome is not None:
            raise outcome

    _worker(process).run_once(db_session)

    assert (
        db_session.scalar(
            select(GitHubRepository.description).where(GitHubRepository.id == repository.id)
        )
        == "before"
    )


def test_what_the_processor_commits_is_kept(db_session):
    repository = _repository(db_session, description="before")
    job_id = _job(db_session, repository)

    def process(db, job):
        db.execute(
            update(GitHubRepository)
            .where(GitHubRepository.id == repository.id)
            .values(description="after")
        )
        db.commit()

    _worker(process).run_once(db_session)

    assert (
        db_session.scalar(
            select(GitHubRepository.description).where(GitHubRepository.id == repository.id)
        )
        == "after"
    )
    assert _state(db_session, job_id)["status"] == "SYNCED"


def test_only_a_bug_is_logged_with_a_traceback(db_session, worker_log):
    _job(db_session)
    _job(db_session)
    _worker(_raises(GitHubUnavailable("timeout"))).run_once(db_session)
    assert all(r.exc_info is None for r in _worker_records(worker_log))

    worker_log.clear()
    _worker(_raises(RuntimeError("bug"))).run_once(db_session)

    with_traceback = [r for r in _worker_records(worker_log) if r.exc_info]
    assert len(with_traceback) == 1
    assert with_traceback[0].levelno == logging.ERROR


# ---------------------------------------------------------------------------
# Rate limits and credentials
# ---------------------------------------------------------------------------


def test_a_rate_limited_job_waits_for_the_reset_without_an_attempt(db_session):
    job_id = _job(db_session, attempt_count=4, last_error="GITHUB_UNAVAILABLE")
    reset = T0 + timedelta(minutes=20)
    worker = _worker(_raises(GitHubRateLimited(reset)))

    assert worker.run_once(db_session) is True

    assert _state(db_session, job_id) == {
        "status": "QUEUED",
        "attempt_count": 4,
        "scheduled_at": reset,
        "last_error": "GITHUB_UNAVAILABLE",
        "updated_at": T0,
    }
    with pytest.raises(GitHubRateLimited):
        worker.client.pause.check(T0 + timedelta(minutes=19))


def test_rate_limits_never_use_up_the_attempts(db_session):
    job_id = _job(db_session, attempt_count=4)
    clock = Clock()

    def limited(db, job):
        raise GitHubRateLimited(clock.now + timedelta(minutes=1))

    for _ in range(8):
        clock.now = _state(db_session, job_id)["scheduled_at"]
        assert _worker(limited, clock).run_once(db_session) is True

    state = _state(db_session, job_id)
    assert (state["status"], state["attempt_count"]) == ("QUEUED", 4)


def test_rejected_credentials_give_the_job_back_and_stop(db_session, worker_log):
    job_id = _job(db_session, attempt_count=1, last_error="GITHUB_UNAVAILABLE")

    with pytest.raises(CredentialsError):
        _worker(_raises(GitHubCredentialsRejected(401))).run_once(db_session)

    state = _state(db_session, job_id)
    assert (state["status"], state["attempt_count"]) == ("QUEUED", 1)
    assert (state["scheduled_at"], state["last_error"]) == (T0, "GITHUB_UNAVAILABLE")
    errors = [r for r in _worker_records(worker_log) if r.levelno == logging.ERROR]
    assert [r.getMessage() for r in errors] == [
        f"Sync job {job_id}: GitHub rejected the app credentials; stopping"
    ]
    assert all("worker_client_secret" not in r.getMessage() for r in worker_log.records)


def _seen(worker: SyncWorker, remaining: int | None, reset_at: datetime | None) -> None:
    worker.client.rate_limits.update(
        RateLimit(limit=5000, remaining=remaining, reset_at=reset_at, used=None, resource="core")
    )


def test_no_claims_during_a_rate_limit_pause(db_session):
    job_id = _job(db_session)
    clock = Clock()
    worker = _worker(_ok, clock)
    worker.client.pause.start(T0 + timedelta(minutes=5))

    assert worker.run_once(db_session) is False
    assert _state(db_session, job_id)["attempt_count"] == 0

    clock.now = T0 + timedelta(minutes=5)
    assert worker.run_once(db_session) is True


def test_a_rate_limited_job_holds_the_other_jobs(db_session):
    first = _job(db_session, scheduled_at=T0 - timedelta(minutes=1))
    second = _job(db_session)
    worker = _worker(_raises(GitHubRateLimited(T0 + timedelta(minutes=10))))

    assert [worker.run_once(db_session) for _ in range(2)] == [True, False]

    assert _state(db_session, first)["scheduled_at"] == T0 + timedelta(minutes=10)
    assert _state(db_session, second)["attempt_count"] == 0


@pytest.mark.parametrize(
    ("reserve", "remaining", "claims"),
    [(500, 500, False), (500, 501, True), (500, 0, False), (0, 0, False), (0, 1, True)],
)
def test_no_claims_within_the_reserve(db_session, monkeypatch, reserve, remaining, claims):
    monkeypatch.setattr(settings, "github_worker_reserve", reserve)
    _job(db_session)
    worker = _worker(_ok)
    _seen(worker, remaining, T0 + timedelta(minutes=30))

    assert worker.run_once(db_session) is claims


def test_the_reserve_holds_until_the_reset(db_session):
    _job(db_session)
    clock = Clock()
    worker = _worker(_ok, clock)
    _seen(worker, 100, T0 + timedelta(minutes=1))

    assert worker.run_once(db_session) is False
    clock.now = T0 + timedelta(minutes=1)
    assert worker.run_once(db_session) is True


@pytest.mark.parametrize(
    ("remaining", "reset_at"), [(None, T0 + timedelta(minutes=30)), (100, None)]
)
def test_an_unknown_budget_does_not_hold_claims(db_session, remaining, reset_at):
    _job(db_session)
    worker = _worker(_ok)
    _seen(worker, remaining, reset_at)

    assert worker.run_once(db_session) is True


def test_no_budget_seen_yet_does_not_hold_claims(db_session):
    _job(db_session)

    assert _worker(_ok).run_once(db_session) is True


def test_the_watchdog_runs_while_claims_are_held(db_session):
    job_id = _job(db_session, status="SYNCING", attempt_count=1, updated_at=T0 - timedelta(hours=1))
    worker = _worker(_ok)
    worker.client.pause.start(T0 + timedelta(minutes=5))

    assert worker.run_once(db_session) is False
    assert _state(db_session, job_id)["last_error"] == "WORKER_LOST"


def test_a_hold_is_logged_when_it_starts_and_ends(db_session, worker_log):
    _job(db_session)
    clock = Clock()
    worker = _worker(_ok, clock)
    _seen(worker, 10, T0 + timedelta(minutes=1))

    for _ in range(3):
        worker.run_once(db_session)
    clock.now = T0 + timedelta(minutes=1)
    worker.run_once(db_session)

    messages = [r.getMessage() for r in _worker_records(worker_log) if "claim" in r.getMessage()]
    assert messages == [
        "GitHub sync worker: no claims, remaining 10 within the reserve until 2026-11-01 12:01:00",
        "GitHub sync worker: claiming",
    ]


# ---------------------------------------------------------------------------
# The startup check
# ---------------------------------------------------------------------------


def _rate_limit_answer(limit: int, remaining: int = 4000, status: int = 200):
    reset = int((T0 + timedelta(minutes=30) - datetime(1970, 1, 1)).total_seconds())
    core = {"limit": limit, "remaining": remaining, "reset": reset, "used": limit - remaining}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rate_limit"
        if status != 200:
            return httpx.Response(status, json={"message": "Bad credentials"})
        return httpx.Response(200, json={"resources": {"core": core}})

    return handler


def test_the_startup_check_accepts_the_app_limit_and_seeds_the_reserve(db_session):
    _job(db_session)
    worker = _worker(_ok, handler=_rate_limit_answer(5000, remaining=400))

    check_credentials(worker.client)

    # The budget read at startup already counts: 400 is within the reserve.
    assert worker.run_once(db_session) is False


@pytest.mark.parametrize(
    "handler",
    [_rate_limit_answer(60, remaining=59), _rate_limit_answer(5000, status=401)],
    ids=["unauthenticated limit", "401"],
)
def test_the_startup_check_refuses_missing_credentials(handler):
    worker = _worker(_ok, handler=handler)

    with pytest.raises(CredentialsError) as exc:
        check_credentials(worker.client)

    assert "worker_client" not in str(exc.value)


def test_the_startup_check_fails_when_github_is_unavailable():
    worker = _worker(_ok, handler=lambda request: httpx.Response(502))

    with pytest.raises(GitHubUnavailable):
        check_credentials(worker.client)


# ---------------------------------------------------------------------------
# The watchdog and the fence
# ---------------------------------------------------------------------------


def test_a_stale_job_is_queued_again(db_session):
    job_id = _job(
        db_session,
        status="SYNCING",
        attempt_count=2,
        scheduled_at=T0 - timedelta(hours=1),
        updated_at=T0 - STALE - timedelta(seconds=1),
    )

    assert recover_stale_jobs(db_session, T0) == 1

    assert _state(db_session, job_id) == {
        "status": "QUEUED",
        "attempt_count": 2,
        "scheduled_at": T0,
        "last_error": "WORKER_LOST",
        "updated_at": T0,
    }


def test_a_job_syncing_for_exactly_the_threshold_is_not_stale(db_session):
    job_id = _job(db_session, status="SYNCING", attempt_count=1, updated_at=T0 - STALE)

    assert recover_stale_jobs(db_session, T0) == 0
    assert _state(db_session, job_id)["status"] == "SYNCING"


def test_the_stale_threshold_is_configurable(db_session, monkeypatch):
    monkeypatch.setattr(settings, "github_worker_stale_seconds", 60)
    job_id = _job(
        db_session, status="SYNCING", attempt_count=1, updated_at=T0 - timedelta(seconds=61)
    )

    assert recover_stale_jobs(db_session, T0) == 1
    assert _state(db_session, job_id)["status"] == "QUEUED"


def test_a_stale_job_with_no_attempts_left_fails(db_session):
    scheduled = T0 - timedelta(hours=1)
    job_id = _job(
        db_session,
        status="SYNCING",
        attempt_count=5,
        scheduled_at=scheduled,
        updated_at=T0 - STALE - timedelta(seconds=1),
    )

    recover_stale_jobs(db_session, T0)

    state = _state(db_session, job_id)
    assert (state["status"], state["attempt_count"]) == ("FAILED", 5)
    assert (state["last_error"], state["scheduled_at"]) == ("WORKER_LOST", scheduled)


def test_run_once_recovers_a_stale_job_and_runs_it(db_session):
    job_id = _job(db_session, status="SYNCING", attempt_count=1, updated_at=T0 - timedelta(hours=1))
    process = Recorder()

    assert _worker(process).run_once(db_session) is True

    assert [job.attempt for job in process.jobs] == [2]
    assert _state(db_session, job_id)["status"] == "SYNCED"


def _taken_back(db: Session, job: ClaimedJob) -> None:
    """What the watchdog and the next claim do while this attempt still runs."""
    db.execute(update(GitHubSyncJob).where(GitHubSyncJob.id == job.id).values(status="QUEUED"))
    db.commit()
    assert claim_job(db, T0).attempt == job.attempt + 1


@pytest.mark.parametrize(
    "outcome",
    [None, GitHubUnavailable("timeout"), GitHubRateLimited(T0 + timedelta(hours=1))],
)
def test_an_attempt_taken_back_does_not_write_its_outcome(db_session, worker_log, outcome):
    job_id = _job(db_session)

    def process(db, job):
        _taken_back(db, job)
        if outcome is not None:
            raise outcome

    _worker(process).run_once(db_session)

    state = _state(db_session, job_id)
    assert (state["status"], state["attempt_count"]) == ("SYNCING", 2)
    assert (state["scheduled_at"], state["last_error"]) == (T0, None)
    assert any("taken back by the watchdog" in r.getMessage() for r in worker_log.records)


# ---------------------------------------------------------------------------
# Two workers: their own sessions on committed rows
# ---------------------------------------------------------------------------


class TestTwoWorkers:
    @pytest.fixture
    def repository_id(self, db_engine):
        github_repo_id = 700_000 + uuid.uuid4().int % 100_000
        with Session(db_engine) as db:
            repository = GitHubRepository(**_repository_fields(github_repo_id=github_repo_id))
            db.add(repository)
            db.commit()
            repository_id = repository.id
        yield repository_id
        with db_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM github_repositories WHERE id = :id"), {"id": repository_id}
            )

    def _jobs(self, db_engine, repository_id, *jobs: dict) -> list[uuid.UUID]:
        """Jobs far in the past, so no other committed row comes before them.
        Only one of them may be active (one active job per repository)."""
        ids = []
        with Session(db_engine) as db:
            for fields in jobs:
                job = GitHubSyncJob(
                    github_repository_id=repository_id,
                    created_at=datetime(2001, 1, 1),
                    updated_at=datetime(2001, 1, 1),
                    **fields,
                )
                db.add(job)
                db.flush()
                ids.append(job.id)
            db.commit()
        return ids

    def test_a_job_locked_by_another_worker_is_skipped(self, db_engine, repository_id):
        (job_id,) = self._jobs(
            db_engine, repository_id, {"status": "QUEUED", "scheduled_at": datetime(2001, 1, 1)}
        )
        process = Recorder()
        with Session(db_engine) as holder, Session(db_engine) as db:
            holder.execute(
                select(GitHubSyncJob.id).where(GitHubSyncJob.id == job_id).with_for_update()
            )

            # Returns at once instead of waiting for the lock; the job is not taken.
            _worker(process).run_once(db)
            holder.rollback()

            assert job_id not in [job.id for job in process.jobs]
            assert _state(db, job_id)["status"] == "QUEUED"

    def test_a_claimed_job_is_not_claimed_again_and_is_not_locked(self, db_engine, repository_id):
        (job_id,) = self._jobs(
            db_engine, repository_id, {"status": "QUEUED", "scheduled_at": datetime(2001, 1, 1)}
        )
        seen: dict = {}

        def first(db, job):
            seen["in_transaction"] = db.in_transaction()
            with Session(db_engine) as other:
                # The claim is committed: the row is not locked and is SYNCING.
                seen["locked"] = other.execute(
                    text("SELECT status FROM github_sync_jobs WHERE id = :id FOR UPDATE NOWAIT"),
                    {"id": job.id},
                ).scalar_one()
                other.rollback()
                second = Recorder()
                _worker(second).run_once(other)
                seen["second"] = [j.id for j in second.jobs]

        with Session(db_engine) as db:
            _worker(first).run_once(db)
            assert _state(db, job_id)["status"] == "SYNCED"

        assert seen == {"in_transaction": False, "locked": "SYNCING", "second": []}

    def test_the_watchdog_skips_a_locked_job(self, db_engine, repository_id):
        (job_id,) = self._jobs(
            db_engine,
            repository_id,
            {"status": "SYNCING", "attempt_count": 1, "scheduled_at": datetime(2001, 1, 1)},
        )
        with Session(db_engine) as holder, Session(db_engine) as db:
            holder.execute(
                select(GitHubSyncJob.id).where(GitHubSyncJob.id == job_id).with_for_update()
            )
            recover_stale_jobs(db, T0)
            assert _state(db, job_id)["status"] == "SYNCING"
            holder.rollback()

            recover_stale_jobs(db, T0)
            assert _state(db, job_id)["status"] == "QUEUED"
