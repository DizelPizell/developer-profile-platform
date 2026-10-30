from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.github import service
from app.github.budget import UserRequestBudget
from app.github.client import GitHubApiClient
from app.github.constants import MAX_LIST_PAGE
from app.github.dependencies import (
    get_github_api_client,
    get_now,
    get_repository_page_cache,
    get_user_request_budget,
)
from app.github.page_cache import RepositoryPageCache
from app.github.schemas import GitHubRepositoryListResponse
from app.models.identity import User

router = APIRouter(prefix="/integrations/github", tags=["github"])


@router.get("/repositories")
def list_repositories(
    page: int = Query(1, ge=1, le=MAX_LIST_PAGE),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    client: GitHubApiClient = Depends(get_github_api_client),
    budget: UserRequestBudget = Depends(get_user_request_budget),
    cache: RepositoryPageCache = Depends(get_repository_page_cache),
    now: datetime = Depends(get_now),
) -> GitHubRepositoryListResponse:
    return service.list_repositories(
        db, user, page, client=client, budget=budget, cache=cache, now=now
    )
