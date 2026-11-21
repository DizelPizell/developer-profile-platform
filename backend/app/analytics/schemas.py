import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EventIn(BaseModel):
    """One event from a public page (ADR-0029). Ids are checked by the service:
    an unknown or hidden profile or project is dropped, not rejected."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["PROFILE_VIEW", "PROJECT_VIEW", "DEMO_CLICK", "GITHUB_CLICK", "CONTACT_CLICK"]
    slug: str = Field(max_length=100)
    project_id: str | None = Field(default=None, max_length=36)


class ProjectCounts(BaseModel):
    project_views: int
    demo_clicks: int
    github_clicks: int


class ProfileCounts(ProjectCounts):
    """github_clicks counts the repository links and the profile's GitHub link."""

    profile_views: int
    contact_clicks: int


class Period(BaseModel):
    days: int
    # Inclusive UTC days.
    start: date
    end: date


class ProjectAnalyticsItem(BaseModel):
    id: uuid.UUID
    title: str | None
    status: str
    visibility: str
    counts: ProjectCounts


class ProfileAnalyticsResponse(BaseModel):
    period: Period
    totals: ProfileCounts
    # Every own project, in the order of GET /projects, zeros included.
    projects: list[ProjectAnalyticsItem]


class ProjectDay(BaseModel):
    day: date
    counts: ProjectCounts


class ProjectAnalyticsResponse(BaseModel):
    period: Period
    totals: ProjectCounts
    # Every day of the period, oldest first, zeros included.
    daily: list[ProjectDay]
