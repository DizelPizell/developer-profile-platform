from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict

from app.models.identity import PROFILE_TEXT_LIMITS
from app.plain_text import plain_text
from app.projects.schemas import PublicFeaturedProject, PublicProject


def _profile_text(field: str, *, allow_newline: bool = False) -> AfterValidator:
    return plain_text(PROFILE_TEXT_LIMITS[field], allow_newline=allow_newline)


class ProfileUpdate(BaseModel):
    """Partial update: only fields present in the request change; null clears a field."""

    model_config = ConfigDict(extra="forbid")

    display_name: Annotated[str | None, _profile_text("display_name")] = None
    headline: Annotated[str | None, _profile_text("headline")] = None
    bio: Annotated[str | None, _profile_text("bio", allow_newline=True)] = None
    location: Annotated[str | None, _profile_text("location")] = None


class OwnProfileResponse(BaseModel):
    slug: str
    status: str
    display_name: str | None
    headline: str | None
    bio: str | None
    location: str | None
    avatar_url: str | None
    github_login: str


class PublicProfileResponse(BaseModel):
    slug: str
    display_name: str | None
    headline: str | None
    bio: str | None
    location: str | None
    avatar_url: str | None
    github_login: str
    featured: list[PublicFeaturedProject]
    other: list[PublicProject]
