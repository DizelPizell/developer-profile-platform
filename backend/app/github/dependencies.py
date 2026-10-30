"""FastAPI dependencies of the GitHub context.

The rate-limit state, the pause, the budget and the list cache are one per
process (ADR-018); each request gets its own client over them. Tests override
these dependencies with fresh instances and a mock transport.
"""

from collections.abc import Generator
from datetime import UTC, datetime

import httpx

from app.github.budget import UserRequestBudget, user_request_budget
from app.github.client import GitHubApiClient, backend_pause, rate_limit_state
from app.github.page_cache import RepositoryPageCache, repository_page_cache
from app.settings import settings


def get_now() -> datetime:
    """Naive UTC, as stored in the database."""
    return datetime.now(UTC).replace(tzinfo=None)


def get_github_api_client() -> Generator[GitHubApiClient]:
    with httpx.Client() as http_client:
        yield GitHubApiClient(
            http_client,
            settings.github_client_id,
            settings.github_client_secret.get_secret_value(),
            rate_limits=rate_limit_state,
            pause=backend_pause,
        )


def get_user_request_budget() -> UserRequestBudget:
    return user_request_budget


def get_repository_page_cache() -> RepositoryPageCache:
    return repository_page_cache
