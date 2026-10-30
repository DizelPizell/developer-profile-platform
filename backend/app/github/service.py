import logging
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.github.budget import (
    LINK_COST,
    LIST_PAGE_COST,
    GitHubUserLimitReached,
    UserRequestBudget,
)
from app.github.client import (
    GitHubApiClient,
    GitHubCredentialsRejected,
    GitHubError,
    GitHubMoved,
    GitHubNotFound,
    GitHubRateLimited,
    GitHubRepositoryData,
    GitHubUnavailable,
    RepositoryPage,
)
from app.github.page_cache import RepositoryPageCache
from app.github.schemas import (
    GitHubLanguage,
    GitHubRepositoryListItem,
    GitHubRepositoryListResponse,
    GitHubSync,
    ProjectGitHub,
)
from app.models.github import GitHubRepository, ProjectRepository
from app.models.identity import User
from app.models.projects import Project

OWNER = "OWNER"
CONTRIBUTOR = "CONTRIBUTOR"

logger = logging.getLogger(__name__)


def _retry_after(seconds: int) -> dict[str, str]:
    return {"Retry-After": str(seconds)}


def _user_limit_reached(exc: GitHubUserLimitReached) -> AppError:
    return AppError(
        "GITHUB_USER_LIMIT_REACHED",
        "GitHub request limit reached, try again later",
        429,
        {"retry_after_seconds": exc.retry_after_seconds},
        headers=_retry_after(exc.retry_after_seconds),
    )


def _rate_limited(exc: GitHubRateLimited, now: datetime) -> AppError:
    seconds = max(1, math.ceil((exc.retry_at - now).total_seconds()))
    return AppError(
        "GITHUB_RATE_LIMITED",
        "GitHub rate limit reached, try again later",
        503,
        {"retry_after_seconds": seconds},
        headers=_retry_after(seconds),
    )


def _unavailable(reason: str, status: int | None) -> AppError:
    return AppError(
        "GITHUB_UNAVAILABLE",
        "GitHub is unavailable",
        502,
        log_context={"reason": reason, "github_status": status},
    )


def _login_outdated() -> AppError:
    return AppError(
        "GITHUB_LOGIN_OUTDATED",
        "Your GitHub login has changed, sign in again",
        409,
        log_context={"reason": "login_outdated"},
    )


def _repository_not_found() -> AppError:
    return AppError("GITHUB_REPOSITORY_NOT_FOUND", "GitHub repository not found or not public", 422)


def _relation_not_found() -> AppError:
    return AppError(
        "GITHUB_RELATION_NOT_FOUND",
        "According to GitHub, you are neither the owner of this repository "
        "nor in its contributor list",
        422,
    )


def _already_linked(project_id: uuid.UUID | None) -> AppError:
    return AppError(
        "GITHUB_REPOSITORY_ALREADY_LINKED",
        "Another of your projects already links this repository",
        409,
        {"project_id": str(project_id) if project_id else None},
    )


def _github_error(exc: GitHubError, now: datetime) -> AppError:
    if isinstance(exc, GitHubRateLimited):
        return _rate_limited(exc, now)
    if isinstance(exc, GitHubCredentialsRejected):
        # The platform's configuration, not the user's request (ADR-016).
        logger.error(
            "GitHub rejected the app credentials; check GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET"
        )
        return AppError(
            "INTERNAL_ERROR",
            "Internal server error",
            500,
            log_context={"reason": "github_credentials_rejected"},
        )
    if isinstance(exc, GitHubUnavailable):
        return _unavailable(exc.reason, exc.status)
    # Unexpected status or a redirect: GitHub answered something the list does not use.
    return _unavailable(type(exc).__name__, getattr(exc, "status", None))


def _own_page(result: RepositoryPage, github_user_id: int) -> RepositoryPage:
    """Only repositories owned by the user's GitHub account.

    A stored login that was renamed may now belong to someone else; their
    repositories are never shown as the user's. A page of only such items means
    the login is outdated.
    """
    own = tuple(item for item in result.items if item.owner_github_id == github_user_id)
    if len(own) < len(result.items):
        logger.warning(
            "GitHub user_repositories: %s items of another owner skipped",
            len(result.items) - len(own),
        )
        if not own:
            raise _login_outdated()
    return RepositoryPage(items=own, has_next=result.has_next)


def _linked_projects(
    db: Session, owner_id: uuid.UUID, github_repo_ids: list[int]
) -> dict[int, uuid.UUID]:
    """The user's own project linking each repository; one query per page."""
    if not github_repo_ids:
        return {}
    rows = db.execute(
        select(GitHubRepository.github_repo_id, ProjectRepository.project_id)
        .join(GitHubRepository, GitHubRepository.id == ProjectRepository.github_repository_id)
        .where(
            ProjectRepository.owner_id == owner_id,
            GitHubRepository.github_repo_id.in_(github_repo_ids),
        )
    )
    return {github_repo_id: project_id for github_repo_id, project_id in rows}


def list_repositories(
    db: Session,
    user: User,
    page: int,
    *,
    client: GitHubApiClient,
    budget: UserRequestBudget,
    cache: RepositoryPageCache,
    now: datetime,
) -> GitHubRepositoryListResponse:
    """One page of the user's public repositories (ADR-017).

    Order of checks (ADR-018): the cache, which costs nothing; the user's budget
    (429); the platform pause (503, in the client); GitHub.
    """
    result = cache.get(user.id, page, now)
    if result is None:
        try:
            with budget.spend(user.id, LIST_PAGE_COST, now, client):
                fetched = client.list_user_repositories(user.github_login, page)
        except GitHubUserLimitReached as exc:
            raise _user_limit_reached(exc) from None
        except GitHubNotFound:
            # GitHub has no user with the stored login: it was renamed since sign-in.
            raise _login_outdated() from None
        except GitHubError as exc:
            raise _github_error(exc, now) from None
        result = _own_page(fetched, user.github_user_id)
        cache.put(user.id, page, result, now)

    linked = _linked_projects(db, user.id, [item.github_repo_id for item in result.items])
    return GitHubRepositoryListResponse(
        items=[
            GitHubRepositoryListItem(
                github_repo_id=item.github_repo_id,
                full_name=item.full_name,
                html_url=item.html_url,
                description=item.description,
                is_fork=item.is_fork,
                is_archived=item.is_archived,
                pushed_at=item.pushed_at.replace(tzinfo=UTC) if item.pushed_at else None,
                linked_project_id=linked.get(item.github_repo_id),
            )
            for item in result.items
        ],
        next_page=page + 1 if result.has_next else None,
    )


# Linking (ADR-017).


@dataclass(frozen=True)
class CheckedRepository:
    data: GitHubRepositoryData
    relation: str


def _read_repository(client: GitHubApiClient, owner: str, name: str) -> GitHubRepositoryData:
    try:
        return client.get_repository(owner, name)
    except GitHubMoved as moved:
        # An old name of a renamed or transferred repository: GitHub points to its id
        # (ADR-017), so it is read by that id with one more request.
        return client.get_repository_by_id(moved.repository_id)


def check_repository(
    full_name: str,
    user_id: uuid.UUID,
    github_user_id: int,
    *,
    client: GitHubApiClient,
    budget: UserRequestBudget,
    now: datetime,
) -> CheckedRepository:
    """The repository and the developer's relation to it, read from GitHub.

    Touches no database: the caller ends its read transaction first, so no
    transaction stays open while GitHub answers (ADR-010). The contributor list
    is read only to find the developer's id in it and is not kept (ADR-017).
    """
    owner, _, name = full_name.partition("/")
    try:
        with budget.spend(user_id, LINK_COST, now, client):
            data = _read_repository(client, owner, name)
            if data.owner_github_id == github_user_id:
                return CheckedRepository(data, OWNER)
            if client.is_contributor(data.owner_login, data.name, github_user_id):
                return CheckedRepository(data, CONTRIBUTOR)
    except GitHubUserLimitReached as exc:
        raise _user_limit_reached(exc) from None
    except GitHubNotFound:
        raise _repository_not_found() from None
    except GitHubError as exc:
        raise _github_error(exc, now) from None
    raise _relation_not_found()


def store_link(db: Session, project: Project, checked: CheckedRepository, now: datetime) -> None:
    """Upserts the shared repository row and replaces the project's link.

    Runs in the caller's write transaction, with the project row locked, so links
    of one project are serialized; the database's unique constraints decide races
    between projects. Nothing is committed here.
    """
    data = checked.data
    metadata = {
        "owner_github_id": data.owner_github_id,
        "owner_login": data.owner_login,
        "name": data.name,
        "full_name": data.full_name,
        "html_url": data.html_url,
        "description": data.description,
        "is_fork": data.is_fork,
        "parent_full_name": data.parent_full_name,
        "is_archived": data.is_archived,
        "pushed_at": data.pushed_at,
    }
    # Languages are left to the sync (ADR-018); a successful read of the metadata
    # clears unavailable_since.
    repository_id = db.execute(
        pg_insert(GitHubRepository)
        .values(github_repo_id=data.github_repo_id, **metadata)
        .on_conflict_do_update(
            index_elements=[GitHubRepository.github_repo_id],
            set_={**metadata, "unavailable_since": None, "updated_at": now},
        )
        .returning(GitHubRepository.id)
    ).scalar_one()

    db.execute(delete(ProjectRepository).where(ProjectRepository.project_id == project.id))
    try:
        with db.begin_nested():
            db.execute(
                insert(ProjectRepository).values(
                    project_id=project.id,
                    owner_id=project.owner_id,
                    github_repository_id=repository_id,
                    relation=checked.relation,
                    relation_checked_at=now,
                )
            )
    except IntegrityError as exc:
        if (
            getattr(exc.orig.diag, "constraint_name", None)
            != "uq_project_repositories_owner_repository"
        ):
            raise
        linked = db.scalar(
            select(ProjectRepository.project_id).where(
                ProjectRepository.owner_id == project.owner_id,
                ProjectRepository.github_repository_id == repository_id,
            )
        )
        raise _already_linked(linked) from None


def unlink(db: Session, project: Project) -> None:
    """Removes the project's link; the shared repository row stays (ADR-017)."""
    db.execute(delete(ProjectRepository).where(ProjectRepository.project_id == project.id))


def _utc(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value else None


def _languages(value: dict | None) -> list[GitHubLanguage]:
    # Ordered when read: bytes descending, then name (ADR-017).
    items = sorted((value or {}).items(), key=lambda item: (-item[1], item[0]))
    return [GitHubLanguage(name=name, bytes=size) for name, size in items]


def project_github(db: Session, project_id: uuid.UUID) -> ProjectGitHub | None:
    """The cabinet's `github` object of a project, or None when it has no link."""
    row = db.execute(
        select(GitHubRepository, ProjectRepository.relation)
        .join(ProjectRepository, ProjectRepository.github_repository_id == GitHubRepository.id)
        .where(ProjectRepository.project_id == project_id)
    ).first()
    if row is None:
        return None
    repository, relation = row
    return ProjectGitHub(
        github_repo_id=repository.github_repo_id,
        full_name=repository.full_name,
        html_url=repository.html_url,
        description=repository.description,
        languages=_languages(repository.languages),
        pushed_at=_utc(repository.pushed_at),
        is_fork=repository.is_fork,
        parent_full_name=repository.parent_full_name,
        is_archived=repository.is_archived,
        relation=relation,
        unavailable=repository.unavailable_since is not None,
        # No sync jobs before step 6.2 (ADR-018): never synced, a manual sync allowed.
        synced_at=None,
        sync=GitHubSync(status="NOT_SYNCED", last_success_at=None, next_manual_sync_at=None),
    )
