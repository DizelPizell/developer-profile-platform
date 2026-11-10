import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import Row, delete, insert, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models.identity import GitHubAccount, Profile, ProfileContact, User

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


def contacts(db: Session, profile_id: uuid.UUID) -> list[Row]:
    """(type, value, label) of the profile's contacts, in position order."""
    return list(
        db.execute(
            select(ProfileContact.type, ProfileContact.value, ProfileContact.label)
            .where(ProfileContact.profile_id == profile_id)
            .order_by(ProfileContact.position)
        )
    )


def _replace_contacts(db: Session, profile: Profile, items: list[dict]) -> bool:
    """Replaces the list whole; False when the normalized list equals the stored one.
    The caller holds the profile row lock."""
    new = [(item["type"], item["value"], item["label"]) for item in items]
    if [tuple(row) for row in contacts(db, profile.id)] == new:
        return False
    # DELETE before INSERT explicitly: left to the unit of work, the inserts could
    # run first and break uq_profile_contacts_position (ADR-020).
    db.execute(delete(ProfileContact).where(ProfileContact.profile_id == profile.id))
    if new:
        db.execute(
            insert(ProfileContact),
            [
                {
                    "profile_id": profile.id,
                    "type": contact_type,
                    "value": value,
                    "label": label,
                    "position": position,
                }
                for position, (contact_type, value, label) in enumerate(new, start=1)
            ],
        )
    return True


def update_profile(
    db: Session,
    profile: Profile,
    changes: dict[str, str | None],
    contact_items: list[dict] | None = None,
) -> None:
    """contact_items None keeps the contacts; a list replaces them."""
    if profile.status == PUBLISHED:
        resulting = {f: changes.get(f, getattr(profile, f)) for f in REQUIRED_FOR_PUBLICATION}
        missing = _missing_for_publication(resulting)
        if missing:
            raise _incomplete(missing)

    changed = contact_items is not None and _replace_contacts(db, profile, contact_items)
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


def contact_value(db: Session, profile_id: uuid.UUID, contact_type: str) -> str | None:
    """The stored value of one standard contact, or None."""
    return db.execute(
        select(ProfileContact.value).where(
            ProfileContact.profile_id == profile_id, ProfileContact.type == contact_type
        )
    ).scalar_one_or_none()
