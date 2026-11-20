from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EventIn(BaseModel):
    """One event from a public page (ADR-0029). Ids are checked by the service:
    an unknown or hidden profile or project is dropped, not rejected."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["PROFILE_VIEW", "PROJECT_VIEW", "DEMO_CLICK", "GITHUB_CLICK", "CONTACT_CLICK"]
    slug: str = Field(max_length=100)
    project_id: str | None = Field(default=None, max_length=36)
