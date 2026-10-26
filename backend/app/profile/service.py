import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models.identity import GitHubAccount, Profile, User

PRIVATE = "PRIVATE"
PUBLISHED = "PUBLISHED"
REQUIRED_FOR_PUBLICATION = ("display_name", "headline")

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,37}[a-z0-9]$")


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _missing_for_publication(values: dict[str, str | None]) -> list[str]:
    return [field for field in REQUIRED_FOR_PUBLICATION if values.get(field) is None]


def _incomplete(missing: list[str]) -> AppError:
    return AppError(
        "PROFILE_INCOMPLETE",
        "Profile is missing fields required for publication",
        422,
        {"missing_fields": missing},
    )


def get_own_profile(db: Session, user: User, *, for_update: bool = False) -> Profile:
    stmt = select(Profile).where(Profile.user_id == user.id)
    if for_update:
        # Serializes PATCH/publish/unpublish so the publication invariant is checked
        # against the row that will actually be written.
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one()


def update_profile(db: Session, profile: Profile, changes: dict[str, str | None]) -> None:
    if profile.status == PUBLISHED:
        resulting = {f: changes.get(f, getattr(profile, f)) for f in REQUIRED_FOR_PUBLICATION}
        missing = _missing_for_publication(resulting)
        if missing:
            raise _incomplete(missing)

    changed = False
    for field, value in changes.items():
        if getattr(profile, field) != value:
            setattr(profile, field, value)
            changed = True
    if changed:
        profile.updated_at = _utcnow()
        db.flush()


def publish(db: Session, profile: Profile) -> None:
    if profile.status == PUBLISHED:
        return
    missing = _missing_for_publication({f: getattr(profile, f) for f in REQUIRED_FOR_PUBLICATION})
    if missing:
        raise _incomplete(missing)
    profile.status = PUBLISHED
    profile.updated_at = _utcnow()
    db.flush()


def unpublish(db: Session, profile: Profile) -> None:
    if profile.status == PRIVATE:
        return
    profile.status = PRIVATE
    profile.updated_at = _utcnow()
    db.flush()


def get_public_profile(db: Session, slug: str) -> tuple[Profile, User, GitHubAccount | None] | None:
    """A PUBLISHED profile by slug (case-insensitive); None for anything else."""
    slug = slug.lower()
    if not _SLUG_RE.fullmatch(slug):
        return None
    row = db.execute(
        select(Profile, User, GitHubAccount)
        .join(User, Profile.user_id == User.id)
        .outerjoin(GitHubAccount, GitHubAccount.user_id == User.id)
        .where(Profile.slug == slug, Profile.status == PUBLISHED)
    ).first()
    return (row[0], row[1], row[2]) if row else None
