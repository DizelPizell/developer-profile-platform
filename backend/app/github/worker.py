"""The GitHub sync worker (ADR-009, ADR-018): a separate process that takes jobs
from github_sync_jobs one at a time and retries failures with a growing delay.

A job is claimed in a short transaction (SKIP LOCKED) that marks it SYNCING and
counts the attempt. The processor runs after that commit, outside any
transaction of the worker, and commits its own writes; anything it leaves
uncommitted is rolled back. The outcome is written in another short
transaction, fenced by the claimed attempt: if the watchdog took the job back
in between, the outcome is dropped instead of overwriting the next attempt.

The processor that reads GitHub comes in step 6.4; here it is a function.
"""

import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import case, select, update
from sqlalchemy.orm import Session

from app.github.client import (
    GitHubApiClient,
    GitHubCredentialsRejected,
    GitHubError,
    GitHubNotFound,
    GitHubRateLimited,
    GitHubUnavailable,
)
from app.github.dependencies import get_now
from app.models.github import SYNC_ERROR_PATTERN, GitHubSyncJob
from app.settings import settings

logger = logging.getLogger(__name__)

# last_error labels of a job (ADR-018: a fixed label, never GitHub's text).
NOT_FOUND = "NOT_FOUND"
GITHUB_UNAVAILABLE = "GITHUB_UNAVAILABLE"
UNEXPECTED_STATUS = "UNEXPECTED_STATUS"
WORKER_LOST = "WORKER_LOST"
INTERNAL_ERROR = "INTERNAL_ERROR"


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
    """GitHub rejected the app credentials; the worker stops (ADR-016)."""


Processor = Callable[[Session, ClaimedJob], None]


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

    def run_once(self, db: Session) -> bool:
        """The watchdog, then at most one job. Returns whether a job was run."""
        now = self.now()
        recover_stale_jobs(db, now)
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
        except GitHubNotFound:
            error = NOT_FOUND
        except GitHubUnavailable:
            error = GITHUB_UNAVAILABLE
        except GitHubError:
            # A redirect the processor did not follow, or a status not in ADR-018.
            error = UNEXPECTED_STATUS
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
