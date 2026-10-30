import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from pydantic_core import PydanticCustomError

from app.github.constants import NAME_PATTERN, OWNER_PATTERN


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


def _not_dot_name(value: str) -> str:
    # The pattern allows them; GitHub has no repository called "." or "..".
    if value.partition("/")[2] in {".", ".."}:
        raise PydanticCustomError("string_pattern_mismatch", "Invalid repository name")
    return value


class RepositoryLinkRequest(BaseModel):
    """Body of POST /projects/{id}/repository: owner/name, checked before GitHub (ADR-016)."""

    model_config = ConfigDict(extra="forbid")

    full_name: Annotated[
        str,
        Field(max_length=140, pattern=f"^{OWNER_PATTERN.pattern}/{NAME_PATTERN.pattern}$"),
        AfterValidator(_not_dot_name),
    ]


class GitHubLanguage(BaseModel):
    name: str
    bytes: int


class GitHubSync(BaseModel):
    status: Literal["NOT_SYNCED", "QUEUED", "SYNCING", "SYNCED", "FAILED"]
    last_success_at: datetime | None
    next_manual_sync_at: datetime | None


class ProjectGitHub(BaseModel):
    """The linked repository as the cabinet sees it (ADR-017, ADR-018)."""

    github_repo_id: int
    full_name: str
    html_url: str
    description: str | None
    languages: list[GitHubLanguage]
    pushed_at: datetime | None
    is_fork: bool
    parent_full_name: str | None
    is_archived: bool
    relation: Literal["OWNER", "CONTRIBUTOR", "NONE"]
    unavailable: bool
    synced_at: datetime | None
    sync: GitHubSync
