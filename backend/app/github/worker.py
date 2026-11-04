"""The GitHub sync worker (ADR-009, ADR-018): a separate process that takes jobs
from github_sync_jobs one at a time and retries failures with a growing delay.

A job is claimed in a short transaction (SKIP LOCKED) that marks it SYNCING and
counts the attempt. The processor runs after that commit, outside any
transaction of the worker, and commits its own writes; anything it leaves
uncommitted is rolled back. The outcome is written in another short
transaction, fenced by the claimed attempt: if the watchdog took the job back
in between, the outcome is dropped instead of overwriting the next attempt.

The processor that reads GitHub is app.github.sync. Run the process with
`python -m app.github.worker`.
"""

import logging
import re
import signal
import sys
import threading
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
from sqlalchemy import DateTime, case, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.github.client import (
    GitHubApiClient,
    GitHubCredentialsRejected,
    GitHubError,
    GitHubNotFound,
    GitHubRateLimited,
    GitHubUnavailable,
    RateLimitPause,
    RateLimitState,
)
from app.github.dependencies import get_now
from app.models.github import (
    ACTIVE_SYNC_JOB_STATUSES,
    SYNC_ERROR_PATTERN,
    GitHubRepository,
    GitHubSyncJob,
    ProjectRepository,
)
from app.models.projects import Project
from app.settings import settings

logger = logging.getLogger(__name__)

# last_error labels of a job (ADR-018: a fixed label, never GitHub's text).
NOT_FOUND = "NOT_FOUND"
GITHUB_UNAVAILABLE = "GITHUB_UNAVAILABLE"
UNEXPECTED_STATUS = "UNEXPECTED_STATUS"
WORKER_LOST = "WORKER_LOST"
INTERNAL_ERROR = "INTERNAL_ERROR"

# Without credentials GitHub allows 60 requests an hour; app credentials get 5,000.
UNAUTHENTICATED_LIMIT = 60

# How often the worker looks for repositories due a periodic sync (ADR-018).
PERIODIC_ENQUEUE_INTERVAL = timedelta(minutes=1)


@dataclass(frozen=True)
class ClaimedJob:
    id: uuid.UUID
    github_repository_id: uuid.UUID
    # attempt_count after the claim; the outcome is written only while it holds.
    attempt: int


class SyncFailed(Exception):
    """A failure the processor classified itself: a label, and whether a retry
    is pointless (as after the second 404 in a row, step 6.5)."""

    def __init__(self, error: str, *, final: bool = False) -> None:
        if not re.fullmatch(SYNC_ERROR_PATTERN, error):
            raise ValueError("A sync error is a fixed label such as NOT_FOUND")
        super().__init__(error)
        self.error = error
        self.final = final


class CredentialsError(Exception):
    """GitHub rejected the app credentials, or did not count them; the worker
    stops (ADR-016). It never falls back to unauthenticated requests."""


Processor = Callable[[Session, ClaimedJob], None]
SessionFactory = Callable[[], AbstractContextManager[Session]]


def check_credentials(client: GitHubApiClient) -> None:
    """The startup check (ADR-018): /rate_limit must answer with the app's
    limit. Its answer also seeds the rate-limit state that the reserve reads."""
    try:
        rate = client.get_rate_limit()
    except GitHubCredentialsRejected:
        raise CredentialsError("GitHub rejected the app credentials") from None
    if rate.limit is None or rate.limit <= UNAUTHENTICATED_LIMIT:
        raise CredentialsError("GitHub did not count the app credentials")
    logger.info(
        "GitHub sync worker: core limit %s, remaining %s, reset at %s",
        rate.limit,
        rate.remaining,
        rate.reset_at,
    )


def github_error_label(exc: GitHubError) -> str | None:
    """The last_error label of a GitHub error (ADR-018), or None for a rate limit
    and rejected credentials, which are not failures of the job."""
    if isinstance(exc, (GitHubRateLimited, GitHubCredentialsRejected)):
        return None
    if isinstance(exc, GitHubNotFound):
        return NOT_FOUND
    if isinstance(exc, GitHubUnavailable):
        return GITHUB_UNAVAILABLE
    # A redirect the processor did not follow, or a status not in ADR-018.
    return UNEXPECTED_STATUS


def retry_delay(attempt: int) -> timedelta:
    """ADR-009's backoff: the base delay after the first attempt, doubled after
    each next one, up to the maximum."""
    base = settings.github_worker_retry_base_seconds
    # The exponent is capped only to keep the number small; the maximum applies anyway.
    seconds = base * 2 ** min(attempt - 1, 32)
    return timedelta(seconds=min(seconds, settings.github_worker_retry_max_seconds))


def recover_stale_jobs(db: Session, now: datetime) -> int:
    """The watchdog (ADR-009): a job left SYNCING longer than the stale
    threshold lost its worker. It is queued again under the same attempt limit,
    or FAILED when the attempts are used up. Locked rows are skipped."""
    cutoff = now - timedelta(seconds=settings.github_worker_stale_seconds)
    stale = (
        select(GitHubSyncJob.id)
        .where(GitHubSyncJob.status == "SYNCING", GitHubSyncJob.updated_at < cutoff)
        .with_for_update(skip_locked=True)
    )
    exhausted = GitHubSyncJob.attempt_count >= settings.github_worker_max_attempts
    rows = db.execute(
        update(GitHubSyncJob)
        .where(GitHubSyncJob.id.in_(stale))
        .values(
            status=case((exhausted, "FAILED"), else_="QUEUED"),
            scheduled_at=case((exhausted, GitHubSyncJob.scheduled_at), else_=now),
            last_error=WORKER_LOST,
            updated_at=now,
        )
        .returning(
            GitHubSyncJob.id,
            GitHubSyncJob.github_repository_id,
            GitHubSyncJob.attempt_count,
            GitHubSyncJob.status,
        )
        .execution_options(synchronize_session=False)
    ).all()
    db.commit()
    for job_id, repository_id, attempt, status in rows:
        logger.warning(
            "Sync job %s of repository %s: lost in SYNCING at attempt %s, now %s",
            job_id,
            repository_id,
            attempt,
            status,
        )
    return len(rows)


def enqueue_periodic_syncs(db: Session, now: datetime) -> int:
    """Queues a job for repositories linked to a PUBLISHED project, whatever its
    visibility, with no job created in the last period and none active (ADR-018).
    At most a batch at a time, so a manual sync never waits behind a long queue;
    the repositories queued leave the selection, so the rest come with the next
    calls, in any order. Returns how many were queued."""
    cutoff = now - timedelta(seconds=settings.github_periodic_sync_seconds)
    published = (
        select(ProjectRepository.id)
        .join(Project, Project.id == ProjectRepository.project_id)
        .where(
            ProjectRepository.github_repository_id == GitHubRepository.id,
            Project.status == "PUBLISHED",
        )
        .exists()
    )
    # An old active job counts here too: left to the unique index, such
    # repositories would take places in the batch on every call.
    recent = (
        select(GitHubSyncJob.id)
        .where(
            GitHubSyncJob.github_repository_id == GitHubRepository.id,
            or_(
                GitHubSyncJob.created_at > cutoff,
                GitHubSyncJob.status.in_(ACTIVE_SYNC_JOB_STATUSES),
            ),
        )
        .exists()
    )
    time = literal(now, DateTime)
    due = (
        select(GitHubRepository.id, literal("QUEUED"), time, time, time)
        .where(published, ~recent)
        .limit(settings.github_periodic_sync_batch)
    )
    queued = db.execute(
        pg_insert(GitHubSyncJob)
        .from_select(
            ["github_repository_id", "status", "scheduled_at", "created_at", "updated_at"], due
        )
        .on_conflict_do_nothing(
            index_elements=[GitHubSyncJob.github_repository_id],
            index_where=GitHubSyncJob.status.in_(ACTIVE_SYNC_JOB_STATUSES),
        )
        .returning(GitHubSyncJob.id)
    ).all()
    db.commit()
    return len(queued)


def claim_job(db: Session, now: datetime) -> ClaimedJob | None:
    """Takes the due QUEUED job scheduled earliest, skipping rows another worker
    has locked, and commits it as SYNCING with the attempt counted."""
    due = (
        select(GitHubSyncJob.id)
        .where(GitHubSyncJob.status == "QUEUED", GitHubSyncJob.scheduled_at <= now)
        .order_by(GitHubSyncJob.scheduled_at, GitHubSyncJob.id)
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    row = db.execute(
        update(GitHubSyncJob)
        .where(GitHubSyncJob.id == due)
        .values(status="SYNCING", attempt_count=GitHubSyncJob.attempt_count + 1, updated_at=now)
        .returning(
            GitHubSyncJob.id, GitHubSyncJob.github_repository_id, GitHubSyncJob.attempt_count
        )
        .execution_options(synchronize_session=False)
    ).first()
    db.commit()
    return ClaimedJob(*row) if row is not None else None


def _finish(db: Session, job: ClaimedJob, now: datetime, **values) -> bool:
    """Writes the outcome only if the job is still SYNCING at the claimed attempt."""
    written = db.execute(
        update(GitHubSyncJob)
        .where(
            GitHubSyncJob.id == job.id,
            GitHubSyncJob.status == "SYNCING",
            GitHubSyncJob.attempt_count == job.attempt,
        )
        .values(updated_at=now, **values)
        .returning(GitHubSyncJob.id)
        .execution_options(synchronize_session=False)
    ).first()
    db.commit()
    if written is None:
        logger.warning(
            "Sync job %s: attempt %s was taken back by the watchdog; its outcome is dropped",
            job.id,
            job.attempt,
        )
    return written is not None


class SyncWorker:
    """One worker process: its client's rate-limit state and pause are its own
    (ADR-018), and it makes one request at a time."""

    def __init__(
        self,
        client: GitHubApiClient,
        process: Processor,
        *,
        now: Callable[[], datetime] = get_now,
    ) -> None:
        self.client = client
        self.process = process
        self.now = now
        self._hold: str | None = None
        self._next_enqueue: datetime | None = None

    def hold_reason(self, now: datetime) -> str | None:
        """Why no job may be claimed now (ADR-018), or None.

        The rate-limit pause holds until the reset it was given. The reserve
        holds while the latest remaining budget seen is at or below it, until
        that answer's reset. Without a known remaining or reset the worker
        claims: only its own requests would tell it more."""
        try:
            self.client.pause.check(now)
        except GitHubRateLimited as exc:
            return f"rate limited until {exc.retry_at}"
        latest = self.client.rate_limits.latest
        if latest is None or latest.remaining is None or latest.reset_at is None:
            return None
        if latest.reset_at > now and latest.remaining <= settings.github_worker_reserve:
            return f"remaining {latest.remaining} within the reserve until {latest.reset_at}"
        return None

    def run_forever(
        self,
        sessions: SessionFactory,
        stop: threading.Event,
        *,
        wait: Callable[[float], object] | None = None,
    ) -> None:
        """The process's loop: the startup check, then jobs one after another,
        with a poll interval when none is due. A stop request ends it after
        the current job. Rejected credentials end it with CredentialsError;
        any other failure of an iteration (the database, say) is logged and
        retried after a poll."""
        wait = wait or stop.wait
        check_credentials(self.client)
        logger.info("GitHub sync worker: started")
        while not stop.is_set():
            try:
                with sessions() as db:
                    ran = self.run_once(db)
            except CredentialsError:
                raise
            except Exception:
                logger.exception("GitHub sync worker: an iteration failed")
                ran = False
            if not ran:
                wait(settings.github_worker_poll_seconds)
        logger.info("GitHub sync worker: stopped")

    def enqueue_due(self, db: Session, now: datetime) -> None:
        """Periodic syncs, at most once a minute (ADR-018). The time moves first:
        an enqueue that fails costs one iteration a minute, the others still claim."""
        if self._next_enqueue is not None and now < self._next_enqueue:
            return
        self._next_enqueue = now + PERIODIC_ENQUEUE_INTERVAL
        queued = enqueue_periodic_syncs(db, now)
        if queued:
            logger.info("GitHub sync worker: %s periodic syncs queued", queued)

    def run_once(self, db: Session) -> bool:
        """The watchdog, the periodic enqueue, then at most one job. Nothing is
        queued or claimed during a hold. Returns whether a job was run."""
        now = self.now()
        recover_stale_jobs(db, now)
        hold = self.hold_reason(now)
        if hold != self._hold:
            # Logged when it starts and ends, not on every poll.
            logger.info("GitHub sync worker: %s", f"no claims, {hold}" if hold else "claiming")
            self._hold = hold
        if hold is not None:
            return False
        self.enqueue_due(db, now)
        job = claim_job(db, now)
        if job is None:
            return False
        logger.info(
            "Sync job %s of repository %s: attempt %s",
            job.id,
            job.github_repository_id,
            job.attempt,
        )
        self._run(db, job)
        return True

    def _run(self, db: Session, job: ClaimedJob) -> None:
        final = False
        try:
            self.process(db, job)
        except GitHubRateLimited as exc:
            # Not a failure (ADR-018): the attempt is given back and the job
            # waits for the reset; the pause stops further claims until then.
            db.rollback()
            self.client.pause.start(exc.retry_at)
            if _finish(
                db,
                job,
                self.now(),
                status="QUEUED",
                attempt_count=job.attempt - 1,
                scheduled_at=exc.retry_at,
            ):
                logger.info("Sync job %s: rate limited, queued until %s", job.id, exc.retry_at)
            return
        except GitHubCredentialsRejected:
            db.rollback()
            _finish(db, job, self.now(), status="QUEUED", attempt_count=job.attempt - 1)
            logger.error("Sync job %s: GitHub rejected the app credentials; stopping", job.id)
            raise CredentialsError("GitHub rejected the app credentials") from None
        except SyncFailed as exc:
            error, final = exc.error, exc.final
        except GitHubError as exc:
            error = github_error_label(exc)
        except Exception:
            # A bug, not GitHub: the only case logged with a traceback. The
            # client's errors are fixed text and are logged by name only.
            logger.exception("Sync job %s: the processor failed", job.id)
            error = INTERNAL_ERROR
        else:
            db.rollback()
            if _finish(db, job, self.now(), status="SYNCED", last_error=None):
                logger.info("Sync job %s: SYNCED", job.id)
            return

        db.rollback()
        now = self.now()
        if final or job.attempt >= settings.github_worker_max_attempts:
            if _finish(db, job, now, status="FAILED", last_error=error):
                logger.warning("Sync job %s: FAILED at attempt %s, %s", job.id, job.attempt, error)
            return
        retry_at = now + retry_delay(job.attempt)
        if _finish(db, job, now, status="QUEUED", scheduled_at=retry_at, last_error=error):
            logger.warning(
                "Sync job %s: %s at attempt %s, retry at %s", job.id, error, job.attempt, retry_at
            )


def install_stop_handlers(stop: threading.Event) -> None:
    """SIGTERM (docker stop) and SIGINT end the loop after the current job.
    The handler only sets the event: logging inside it could deadlock."""

    def handle(signum: int, frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)


def main() -> int:
    """The worker process (ADR-018): its own client, rate-limit state and pause,
    database sessions per iteration, and a stop on SIGTERM or SIGINT. Returns
    the exit code: 0 after a stop, 1 when GitHub refuses the credentials or
    cannot be reached at startup, so the restart policy tries again later."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # The processor imports this module; imported here, there is no cycle.
    from app.github.sync import make_processor

    stop = threading.Event()
    install_stop_handlers(stop)
    with httpx.Client() as http_client:
        client = GitHubApiClient(
            http_client,
            settings.github_client_id,
            settings.github_client_secret.get_secret_value(),
            rate_limits=RateLimitState(),
            pause=RateLimitPause(),
        )
        worker = SyncWorker(client, make_processor(client, get_now))
        try:
            worker.run_forever(SessionLocal, stop)
        except CredentialsError as exc:
            logger.error("GitHub sync worker: %s; exiting", exc)
            return 1
        except GitHubError as exc:
            logger.error(
                "GitHub sync worker: startup check failed, %s; exiting", type(exc).__name__
            )
            return 1
    return 0


if __name__ == "__main__":
    # Run as __main__, this file is a second copy of the module, and the
    # processor would raise the other copy's SyncFailed. The imported module
    # runs instead, so every class has one identity.
    from app.github.worker import main as _main

    sys.exit(_main())
