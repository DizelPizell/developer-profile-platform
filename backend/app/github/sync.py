"""The sync worker's processor (ADR-018, step 6.4): a repository's metadata and
languages read from GitHub and stored, one category at a time, then the
relation of every link to it recomputed (ADR-017).

Everything a write needs is read before its transaction opens, and no
transaction is open while GitHub answers (ADR-010). Each category is written
in its own short transaction with its success in github_sync_category_status
(ADR-011). A failed category leaves its stored data as it was, records its
label, and the error goes on to the worker, which retries the job.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.github.client import (
    GitHubApiClient,
    GitHubCredentialsRejected,
    GitHubError,
    GitHubRepositoryData,
)
from app.github.service import (
    CONTRIBUTOR,
    NONE,
    OWNER,
    record_category_error,
    record_category_success,
    repository_metadata,
)
from app.github.worker import ClaimedJob, Processor, github_error_label
from app.models.github import GitHubRepository, ProjectRepository
from app.models.identity import User

logger = logging.getLogger(__name__)


def make_processor(client: GitHubApiClient, now: Callable[[], datetime]) -> Processor:
    """The processor the worker runs for each job, over the worker's own client."""

    def process(db: Session, job: ClaimedJob) -> None:
        sync_repository(db, client, job.github_repository_id, now)

    return process


def sync_repository(
    db: Session, client: GitHubApiClient, repository_id: uuid.UUID, now: Callable[[], datetime]
) -> None:
    """Metadata by GitHub's repository id, so a renamed or transferred repository
    is found under its new name, then languages under that name."""
    github_repo_id = db.scalar(
        select(GitHubRepository.github_repo_id).where(GitHubRepository.id == repository_id)
    )
    db.rollback()
    if github_repo_id is None:
        # Deleted with its jobs since the claim; the worker's fence drops the outcome.
        return

    data = _read(
        db, repository_id, "metadata", lambda: client.get_repository_by_id(github_repo_id), now
    )
    _store_metadata(db, repository_id, data, now())
    languages = _read(
        db,
        repository_id,
        "languages",
        lambda: client.get_languages(data.owner_login, data.name),
        now,
    )
    _store_languages(db, repository_id, languages, now())
    _recompute_relations(db, client, repository_id, data, now)


def _read[T](
    db: Session,
    repository_id: uuid.UUID,
    category: str,
    read: Callable[[], T],
    now: Callable[[], datetime],
) -> T:
    try:
        return read()
    except GitHubError as exc:
        error = github_error_label(exc)
        if error is not None:
            record_category_error(db, repository_id, category, error, now())
            db.commit()
        raise


def _store_metadata(
    db: Session, repository_id: uuid.UUID, data: GitHubRepositoryData, now: datetime
) -> None:
    # A successful read clears unavailable_since (ADR-017).
    db.execute(
        update(GitHubRepository)
        .where(GitHubRepository.id == repository_id)
        .values(**repository_metadata(data), unavailable_since=None, updated_at=now)
    )
    record_category_success(db, repository_id, "metadata", now)
    db.commit()


def _store_languages(
    db: Session, repository_id: uuid.UUID, languages: dict[str, int], now: datetime
) -> None:
    # Replaced whole, in GitHub's shape (ADR-011, ADR-017).
    db.execute(
        update(GitHubRepository)
        .where(GitHubRepository.id == repository_id)
        .values(languages=languages, updated_at=now)
    )
    record_category_success(db, repository_id, "languages", now)
    db.commit()


def _recompute_relations(
    db: Session,
    client: GitHubApiClient,
    repository_id: uuid.UUID,
    data: GitHubRepositoryData,
    now: Callable[[], datetime],
) -> None:
    """OWNER, CONTRIBUTOR or NONE for every link to the repository, whoever made
    it (ADR-017). The contributor pages are read only for developers who are not
    the owner, and not stored. If they cannot be read, those links keep their
    relation; the job does not fail for it (ADR-018)."""
    links = db.execute(
        select(ProjectRepository.id, User.github_user_id)
        .join(User, User.id == ProjectRepository.owner_id)
        .where(ProjectRepository.github_repository_id == repository_id)
    ).all()
    db.rollback()
    others = {
        github_user_id for _, github_user_id in links if github_user_id != data.owner_github_id
    }
    contributors: set[int] | None = set()
    if others:
        try:
            contributors = client.find_contributors(data.owner_login, data.name, others)
        except GitHubCredentialsRejected:
            raise
        except GitHubError as exc:
            logger.warning(
                "Sync of repository %s: contributors not read (%s), relations kept",
                repository_id,
                type(exc).__name__,
            )
            contributors = None

    relations = {}
    for link_id, github_user_id in links:
        if github_user_id == data.owner_github_id:
            relations[link_id] = OWNER
        elif contributors is not None:
            relations[link_id] = CONTRIBUTOR if github_user_id in contributors else NONE
    checked_at = now()
    for link_id, relation in relations.items():
        # By the link's id: a link replaced meanwhile is a new row and is left alone.
        db.execute(
            update(ProjectRepository)
            .where(ProjectRepository.id == link_id)
            .values(relation=relation, relation_checked_at=checked_at)
        )
    db.commit()
