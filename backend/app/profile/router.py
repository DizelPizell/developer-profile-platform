from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.errors import AppError
from app.models.identity import Profile, User
from app.profile import service
from app.profile.schemas import OwnProfileResponse, ProfileUpdate, PublicProfileResponse
from app.projects import service as projects_service
from app.projects.schemas import PublicFeaturedProject, PublicProject

router = APIRouter(prefix="/profile", tags=["profile"])
public_router = APIRouter(prefix="/public/profiles", tags=["public"])


def _own_profile_response(profile: Profile, user: User) -> OwnProfileResponse:
    return OwnProfileResponse(
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
    return _own_profile_response(service.get_own_profile(db, user), user)


@router.patch("")
def update_profile(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OwnProfileResponse:
    profile = service.get_own_profile(db, user, for_update=True)
    # Only fields present in the request body; an explicit null is a change too.
    service.update_profile(db, profile, payload.model_dump(include=payload.model_fields_set))
    db.commit()
    return _own_profile_response(profile, user)


@router.post("/publish")
def publish_profile(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> OwnProfileResponse:
    profile = service.get_own_profile(db, user, for_update=True)
    service.publish(db, profile)
    db.commit()
    return _own_profile_response(profile, user)


@router.post("/unpublish")
def unpublish_profile(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> OwnProfileResponse:
    profile = service.get_own_profile(db, user, for_update=True)
    service.unpublish(db, profile)
    db.commit()
    return _own_profile_response(profile, user)


@public_router.get("/{slug}")
def get_public_profile(slug: str, db: Session = Depends(get_db)) -> PublicProfileResponse:
    found = service.get_public_profile(db, slug)
    if found is None:
        # Private, missing and malformed slugs are indistinguishable from any unknown URL.
        raise AppError("NOT_FOUND", "Not Found", 404)
    profile, user, github_account = found

    # Two queries for any number of projects and technologies.
    rows = projects_service.public_projects(db, user.id)
    names = projects_service.technology_names(db, [row.id for row in rows])
    featured: list[PublicFeaturedProject] = []
    other: list[PublicProject] = []
    for row in rows:
        card = {
            "id": row.id,
            "title": row.title,
            "summary": row.summary,
            "role": row.role,
            "technologies": names[row.id],
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
        featured=featured,
        other=other,
    )
