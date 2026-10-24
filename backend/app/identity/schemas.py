import uuid

from pydantic import BaseModel


class MeResponse(BaseModel):
    id: uuid.UUID
    github_login: str
    email: str | None
    profile_slug: str | None
