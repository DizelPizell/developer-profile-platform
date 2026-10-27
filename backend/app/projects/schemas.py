import re
import unicodedata
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field
from pydantic_core import PydanticCustomError

from app.canonical_uuid import parse_canonical_uuid
from app.models.projects import (
    FEATURED_PROJECTS_PER_PROFILE,
    PROJECT_TEXT_LIMITS,
    TECHNOLOGIES_PER_PROJECT,
    TECHNOLOGY_NAME_MAX_LENGTH,
)

_WHITESPACE_RUN = re.compile(r"\s+")


def _has_control_characters(value: str, allowed: set[str]) -> bool:
    return any(unicodedata.category(ch) == "Cc" and ch not in allowed for ch in value)


def _project_text(field: str, *, allow_newline: bool = False) -> AfterValidator:
    """Trim all edge whitespace, turn blank into null, reject control characters
    (newlines only where allowed), enforce the length limit (ADR-015)."""
    max_length = PROJECT_TEXT_LIMITS[field]
    allowed_controls = {"\n"} if allow_newline else set()

    def normalize(value: str | None) -> str | None:
        if value is None:
            return None
        if allow_newline:
            value = value.replace("\r\n", "\n")
        value = value.strip()
        if not value:
            return None
        if _has_control_characters(value, allowed_controls):
            raise PydanticCustomError("control_characters", "Control characters are not allowed")
        if len(value) > max_length:
            raise PydanticCustomError("string_too_long", "String is too long")
        return value

    return AfterValidator(normalize)


def _technology_name(value: str) -> str:
    """Trim and collapse whitespace runs to one space; 1–50 characters, no controls."""
    value = _WHITESPACE_RUN.sub(" ", value).strip()
    if not value:
        raise PydanticCustomError("string_too_short", "String is too short")
    if _has_control_characters(value, set()):
        raise PydanticCustomError("control_characters", "Control characters are not allowed")
    if len(value) > TECHNOLOGY_NAME_MAX_LENGTH:
        raise PydanticCustomError("string_too_long", "String is too long")
    return value


def _no_duplicate_technologies(names: list[str]) -> list[str]:
    # Names that differ only in case are one technology (ADR-015); nothing is merged silently.
    if len({name.lower() for name in names}) != len(names):
        raise PydanticCustomError("duplicate_technology", "Technologies must be unique")
    return names


TechnologyName = Annotated[str, AfterValidator(_technology_name)]
TechnologyList = Annotated[
    list[TechnologyName],
    Field(max_length=TECHNOLOGIES_PER_PROJECT),
    AfterValidator(_no_duplicate_technologies),
]


class ProjectWrite(BaseModel):
    """Body of POST /projects and PATCH /projects/{id}.

    Only fields present in the request change; null clears a text field. `technologies`
    replaces the whole list in the given order; it cannot be null ([] clears it).
    """

    model_config = ConfigDict(extra="forbid")

    title: Annotated[str | None, _project_text("title")] = None
    summary: Annotated[str | None, _project_text("summary")] = None
    description: Annotated[str | None, _project_text("description", allow_newline=True)] = None
    problem: Annotated[str | None, _project_text("problem", allow_newline=True)] = None
    results: Annotated[str | None, _project_text("results", allow_newline=True)] = None
    role: Annotated[str | None, _project_text("role")] = None
    contribution: Annotated[str | None, _project_text("contribution", allow_newline=True)] = None
    # Omitted keeps the list; the default is not validated, an explicit null is rejected.
    technologies: TechnologyList = None  # type: ignore[assignment]


class ProjectVisibilityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visibility: Literal["PUBLIC", "PRIVATE"]


class ProjectResponse(BaseModel):
    id: uuid.UUID
    status: str
    visibility: str
    title: str | None
    summary: str | None
    description: str | None
    problem: str | None
    results: str | None
    role: str | None
    contribution: str | None
    technologies: list[str]
    featured_position: int | None


class ProjectSummary(BaseModel):
    id: uuid.UUID
    status: str
    visibility: str
    title: str | None
    summary: str | None
    technologies: list[str]
    featured_position: int | None


class ProjectListResponse(BaseModel):
    items: list[ProjectSummary]


def _canonical_uuid(value: object) -> object:
    # The same form as a project id in the path; other types fail as uuid_type.
    if isinstance(value, str) and parse_canonical_uuid(value) is None:
        raise PydanticCustomError("uuid_parsing", "Input should be a canonical UUID")
    return value


def _no_duplicate_projects(project_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    if len(set(project_ids)) != len(project_ids):
        raise PydanticCustomError("duplicate_project", "Project ids must be unique")
    return project_ids


class FeaturedReorderRequest(BaseModel):
    """The complete current featured set in the new order (ADR-015)."""

    model_config = ConfigDict(extra="forbid")

    project_ids: Annotated[
        list[Annotated[uuid.UUID, BeforeValidator(_canonical_uuid)]],
        Field(max_length=FEATURED_PROJECTS_PER_PROFILE),
        AfterValidator(_no_duplicate_projects),
    ]


class FeaturedProject(BaseModel):
    project_id: uuid.UUID
    position: int


class FeaturedProjectsResponse(BaseModel):
    items: list[FeaturedProject]
