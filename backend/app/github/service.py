import logging
import math
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.github.budget import LIST_PAGE_COST, GitHubUserLimitReached, UserRequestBudget
from app.github.client import (
    GitHubApiClient,
    GitHubCredentialsRejected,
    GitHubError,
    GitHubNotFound,
    GitHubRateLimited,
    GitHubUnavailable,
    RepositoryPage,
)
from app.github.page_cache import RepositoryPageCache
from app.github.schemas import GitHubRepositoryListItem, GitHubRepositoryListResponse
from app.models.github import GitHubRepository, ProjectRepository
from app.models.identity import User

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
