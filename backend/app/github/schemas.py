import uuid
from datetime import datetime

from pydantic import BaseModel


class GitHubRepositoryListItem(BaseModel):
    github_repo_id: int
    full_name: str
    html_url: str
    description: str | None
    is_fork: bool
    is_archived: bool
    pushed_at: datetime | None
    linked_project_id: uuid.UUID | None


class GitHubRepositoryListResponse(BaseModel):
    items: list[GitHubRepositoryListItem]
    next_page: int | None
