from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.errors import AppError
from app.github import service as github_service
from app.models.identity import Profile, User
from app.profile import service
from app.profile.contacts import contact_url
from app.profile.schemas import (
    Contact,
    OwnProfileResponse,
    ProfileUpdate,
    PublicContact,
    PublicContactValue,
    PublicProfileResponse,
)
from app.projects import service as projects_service
from app.projects.schemas import PublicFeaturedProject, PublicProject

router = APIRouter(prefix="/profile", tags=["profile"])
public_router = APIRouter(prefix="/public/profiles", tags=["public"])

# Shown publicly only on request, through GET /public/profiles/{slug}/contacts (ADR-020).
_ON_REQUEST = ("EMAIL", "PHONE")


def _not_found() -> AppError:
    # Private, missing and malformed slugs are indistinguishable from any unknown URL.
    return AppError("NOT_FOUND", "Not Found", 404)


def _own_profile_response(db: Session, profile: Profile, user: User) -> OwnProfileResponse:
    return OwnProfileResponse(
        contacts=[
            Contact(type=t, value=v, label=label, url=contact_url(t, v))
            for t, v, label in service.contacts(db, profile.id)
        ],
        slug=profile.slug,
        status=profile.status,
        display_name=profile.display_name,
        headline=profile.headline,
        bio=profile.bio,
        location=profile.location,
        avatar_url=user.github_account.avatar_url,
        github_login=user.github_login,
    )


@router.get("")
def get_profile(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> OwnProfileResponse:
    return _own_profile_response(db, service.get_own_profile(db, user), user)


@router.patch("")
def update_profile(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OwnProfileResponse:
    profile = service.get_own_profile(db, user, for_update=True)
    # Only fields present in the request body; an explicit null is a change too.
    changes = payload.model_dump(include=payload.model_fields_set)
    service.update_profile(db, profile, changes, changes.pop("contacts", None))
    db.commit()
    return _own_profile_response(db, profile, user)


@router.post("/publish")
def publish_profile(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> OwnProfileResponse:
    profile = service.get_own_profile(db, user, for_update=True)
    service.publish(db, profile)
    db.commit()
    return _own_profile_response(db, profile, user)


@router.post("/unpublish")
def unpublish_profile(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> OwnProfileResponse:
    profile = service.get_own_profile(db, user, for_update=True)
    service.unpublish(db, profile)
    db.commit()
    return _own_profile_response(db, profile, user)


@public_router.get("/{slug}")
def get_public_profile(slug: str, db: Session = Depends(get_db)) -> PublicProfileResponse:
    found = service.get_public_profile(db, slug)
    if found is None:
        raise _not_found()
    profile, user, github_account = found

    # One query for any number of contacts; email and phone only say they exist.
    public_contacts = [
        PublicContact(type=t, value=None, label=None, url=None)
        if t in _ON_REQUEST
        else PublicContact(type=t, value=v, label=label, url=contact_url(t, v))
        for t, v, label in service.contacts(db, profile.id)
    ]

    # Three queries for any number of projects, technologies and repositories.
    rows = projects_service.public_projects(db, user.id)
    project_ids = [row.id for row in rows]
    names = projects_service.technology_names(db, project_ids)
    github = github_service.public_github(db, project_ids)
    featured: list[PublicFeaturedProject] = []
    other: list[PublicProject] = []
    for row in rows:
        card = {
            "id": row.id,
            "title": row.title,
            "summary": row.summary,
            "role": row.role,
            "technologies": names[row.id],
            "github": github.get(row.id),
        }
        if row.position is None:
            other.append(PublicProject(**card))
        else:
            featured.append(PublicFeaturedProject(**card, position=row.position))

    return PublicProfileResponse(
        slug=profile.slug,
        display_name=profile.display_name,
        headline=profile.headline,
        bio=profile.bio,
        location=profile.location,
        avatar_url=github_account.avatar_url if github_account else None,
        github_login=user.github_login,
        contacts=public_contacts,
        featured=featured,
        other=other,
    )


@public_router.get("/{slug}/contacts")
def get_public_contact(
    slug: str,
    contact_type: Annotated[Literal["EMAIL", "PHONE"], Query(alias="type")],
    response: Response,
    db: Session = Depends(get_db),
) -> PublicContactValue:
    """The value of the profile's email or phone, asked for by a click (ADR-020)."""
    # shortcut: no rate limit, so a script can read values one profile at a time;
    # step 8.3 adds the limit (ADR-020, "Negative").
    found = service.get_public_profile(db, slug)
    value = found and service.contact_value(db, found[0].id, contact_type)
    if not value:
        raise _not_found()
    response.headers["Cache-Control"] = "no-store"
    return PublicContactValue(type=contact_type, value=value, url=contact_url(contact_type, value))
