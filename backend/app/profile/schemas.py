import unicodedata
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict
from pydantic_core import PydanticCustomError

from app.models.identity import PROFILE_TEXT_LIMITS
from app.projects.schemas import PublicFeaturedProject, PublicProject


def _profile_text(field: str, *, allow_newline: bool = False) -> AfterValidator:
    """Trim, turn blank into null, reject control characters, enforce the length limit."""
    max_length = PROFILE_TEXT_LIMITS[field]
    allowed_controls = {"\n"} if allow_newline else set()

    def normalize(value: str | None) -> str | None:
        if value is None:
            return None
        if allow_newline:
            value = value.replace("\r\n", "\n")
        value = value.strip()
        if not value:
            return None
        if any(unicodedata.category(ch) == "Cc" and ch not in allowed_controls for ch in value):
            raise PydanticCustomError("control_characters", "Control characters are not allowed")
        if len(value) > max_length:
            raise PydanticCustomError("string_too_long", "String is too long")
        return value

    return AfterValidator(normalize)


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
