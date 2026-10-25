import hashlib
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models.identity import AuthSession, GitHubAccount, Profile, User
from app.settings import settings

RESERVED_SLUGS: frozenset[str] = frozenset(
    {
        "about",
        "admin",
        "api",
        "assets",
        "auth",
        "feed",
        "help",
        "login",
        "logout",
        "me",
        "privacy",
        "profile",
        "profiles",
        "public",
        "robots",
        "rss",
        "settings",
        "sitemap",
        "static",
        "support",
        "terms",
        "www",
    }
)

_INVALID_CHARS_RE = re.compile(r"[^a-z0-9-]")
_MULTI_HYPHEN_RE = re.compile(r"-{2,}")
_MAX_SLUG = 39
_MIN_SLUG = 3
_SUFFIX_LEN = 7  # '-' + 6 hex chars


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _generate_base_slug(github_login: str) -> str:
    slug = github_login.lower()
    slug = _INVALID_CHARS_RE.sub("-", slug)
    slug = _MULTI_HYPHEN_RE.sub("-", slug)
    slug = slug.strip("-")

    # Check reserved words before padding so "me" → "me-0", not "me0"
    if slug in RESERVED_SLUGS:
        slug = slug + "-0"

    # Pad to minimum length
    while len(slug) < _MIN_SLUG:
        slug = (slug + "0") if slug else "user"

    # Truncate and strip trailing hyphen
    slug = slug[:_MAX_SLUG].rstrip("-")

    return slug


def _slug_with_random_suffix(base: str) -> str:
    suffix = secrets.token_hex(3)  # 6 hex chars
    max_base = _MAX_SLUG - _SUFFIX_LEN  # 32
    trimmed = base[:max_base].rstrip("-")
    return f"{trimmed}-{suffix}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _find_user_by_github_id(db: Session, github_user_id: int) -> User | None:
    return db.execute(
        select(User).where(User.github_user_id == github_user_id)
    ).scalar_one_or_none()


def get_or_create_user(
    db: Session,
    github_user_id: int,
    github_login: str,
    email: str | None,
    avatar_url: str | None = None,
) -> tuple[User, bool]:
    """
    Find or create User + GitHubAccount + Profile in one SAVEPOINT.

    Returns (user, is_new). Race condition (concurrent first login) is handled
    by catching IntegrityError and re-reading by github_user_id. If github_user_id
    is not found after IntegrityError, the conflict is a slug collision; we retry
    with a random suffix (up to 5 attempts total).
    """
    base_slug = _generate_base_slug(github_login)

    for attempt in range(5):
        slug = base_slug if attempt == 0 else _slug_with_random_suffix(base_slug)

        try:
            with db.begin_nested():
                # Objects are added INSIDE the SAVEPOINT so that begin_nested()'s
                # pre-flush snapshot (autoflush) finds nothing pending and the
                # SAVEPOINT is created before any INSERT is attempted.
                user = User(github_user_id=github_user_id, github_login=github_login, email=email)
                user.github_account = GitHubAccount(avatar_url=avatar_url)
                user.profile = Profile(slug=slug, status="PRIVATE")
                db.add(user)
                db.flush()
            return user, True
        except IntegrityError:
            existing = _find_user_by_github_id(db, github_user_id)
            if existing is not None:
                return existing, False
            # Slug conflict — retry with a different suffix

    raise AppError("SLUG_CONFLICT", "Could not generate a unique profile slug", 500)


def update_user_fields(
    db: Session,
    user: User,
    github_login: str,
    email: str | None,
    *,
    avatar_url: str | None,
) -> None:
    """Update mutable GitHub fields on repeat login. Slug is never changed here."""
    user.github_login = github_login
    user.email = email
    # A response without a usable avatar keeps the stored one.
    if avatar_url is not None:
        user.github_account.avatar_url = avatar_url
    db.flush()


def create_session(db: Session, user_id: uuid.UUID) -> str:
    """Issue a new session token, storing only its hash. Returns the raw token."""
    token = secrets.token_urlsafe(32)
    token_hash = hash_token(token)
    expires_at = _utcnow() + timedelta(days=settings.session_ttl_days)
    db.add(AuthSession(user_id=user_id, token_hash=token_hash, expires_at=expires_at))
    db.flush()
    return token


def get_session_user(db: Session, token: str) -> User | None:
    """Return the User for a valid, non-expired session token, or None."""
    token_hash = hash_token(token)
    row = db.execute(
        select(AuthSession, User)
        .join(User, AuthSession.user_id == User.id)
        .where(AuthSession.token_hash == token_hash)
        .where(AuthSession.expires_at > _utcnow())
    ).first()
    return row[1] if row else None


def delete_session(db: Session, token: str) -> None:
    """Delete the session row for the given raw token (no-op if not found)."""
    token_hash = hash_token(token)
    session = db.execute(
        select(AuthSession).where(AuthSession.token_hash == token_hash)
    ).scalar_one_or_none()
    if session is not None:
        db.delete(session)
        db.flush()


def get_user_profile(db: Session, user_id: uuid.UUID) -> Profile | None:
    return db.execute(
        select(Profile).where(Profile.user_id == user_id)
    ).scalar_one_or_none()
