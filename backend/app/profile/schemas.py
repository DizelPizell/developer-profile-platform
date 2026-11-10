from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
)
from pydantic_core import PydanticCustomError

from app.models.identity import (
    CONTACT_LABEL_MAX_LENGTH,
    CONTACTS_PER_PROFILE,
    OTHER_CONTACTS_PER_PROFILE,
    PROFILE_TEXT_LIMITS,
)
from app.plain_text import plain_text
from app.profile import contacts
from app.projects.schemas import PublicFeaturedProject, PublicProject

ContactType = Literal["EMAIL", "TELEGRAM", "LINKEDIN", "PHONE", "OTHER"]


def _profile_text(field: str, *, allow_newline: bool = False) -> AfterValidator:
    return plain_text(PROFILE_TEXT_LIMITS[field], allow_newline=allow_newline)


class ContactWrite(BaseModel):
    """One contact of PATCH /profile (ADR-020). The server keeps the normalized
    value and builds the link; a link is never accepted as a field."""

    model_config = ConfigDict(extra="forbid")

    type: ContactType
    value: str
    # Validated when absent too: OTHER requires a name.
    label: Annotated[str | None, plain_text(CONTACT_LABEL_MAX_LENGTH)] = Field(
        None, validate_default=True
    )

    @field_validator("value")
    @classmethod
    def _normalize_value(cls, value: str, info: ValidationInfo) -> str:
        contact_type = info.data.get("type")
        # An invalid type is reported on its own field.
        return contacts.normalize(contact_type, value) if contact_type else value

    @field_validator("label")
    @classmethod
    def _label_for_other_only(cls, label: str | None, info: ValidationInfo) -> str | None:
        contact_type = info.data.get("type")
        if contact_type == "OTHER" and label is None:
            raise PydanticCustomError("missing", "Field required")
        if contact_type not in (None, "OTHER") and label is not None:
            raise PydanticCustomError("label_not_allowed", "Only OTHER contacts have a label")
        return label


def _contact_list_rules(items: list[ContactWrite]) -> list[ContactWrite]:
    standard = [item.type for item in items if item.type != "OTHER"]
    if len(set(standard)) != len(standard):
        raise PydanticCustomError("duplicate_contact_type", "Contact types must be unique")
    # A domain rule: the database holds only the cap of 7 (ADR-020).
    if len(items) - len(standard) > OTHER_CONTACTS_PER_PROFILE:
        raise PydanticCustomError("too_many_other_contacts", "Too many OTHER contacts")
    return items


ContactList = Annotated[
    list[ContactWrite],
    Field(max_length=CONTACTS_PER_PROFILE),
    AfterValidator(_contact_list_rules),
]


class Contact(BaseModel):
    type: str
    value: str
    label: str | None
    url: str


class PublicContact(BaseModel):
    """value and url are null for EMAIL and PHONE: they come on request (ADR-020)."""

    type: str
    value: str | None
    label: str | None
    url: str | None


class PublicContactValue(BaseModel):
    type: str
    value: str
    url: str


class ProfileUpdate(BaseModel):
    """Partial update: only fields present in the request change; null clears a field."""

    model_config = ConfigDict(extra="forbid")

    display_name: Annotated[str | None, _profile_text("display_name")] = None
    headline: Annotated[str | None, _profile_text("headline")] = None
    bio: Annotated[str | None, _profile_text("bio", allow_newline=True)] = None
    location: Annotated[str | None, _profile_text("location")] = None
    # Omitted keeps the list, a list replaces it, [] clears it; the default is not
    # validated, an explicit null is rejected (the rules of technologies, ADR-015).
    contacts: ContactList = None  # type: ignore[assignment]


class OwnProfileResponse(BaseModel):
    slug: str
    status: str
    display_name: str | None
    headline: str | None
    bio: str | None
    location: str | None
    avatar_url: str | None
    github_login: str
    contacts: list[Contact]


class PublicProfileResponse(BaseModel):
    slug: str
    display_name: str | None
    headline: str | None
    bio: str | None
    location: str | None
    avatar_url: str | None
    github_login: str
    contacts: list[PublicContact]
    featured: list[PublicFeaturedProject]
    other: list[PublicProject]
