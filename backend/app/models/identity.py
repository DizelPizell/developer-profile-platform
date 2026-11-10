import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    github_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    github_login: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    github_account: Mapped["GitHubAccount"] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    profile: Mapped["Profile"] = relationship(back_populates="user", cascade="all, delete-orphan")
    auth_sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class GitHubAccount(Base):
    __tablename__ = "github_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    # GitHub data, refreshed on every login.
    avatar_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="github_account")


PROFILE_TEXT_LIMITS: dict[str, int] = {
    "display_name": 100,
    "headline": 160,
    "bio": 2000,
    "location": 100,
}


def _text_check(column: str, max_length: int) -> CheckConstraint:
    return CheckConstraint(
        f"char_length({column}) <= {max_length} AND btrim({column}) <> ''",
        name=f"ck_profiles_{column}",
    )


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("status IN ('PRIVATE', 'PUBLISHED')", name="ck_profiles_status"),
        CheckConstraint(
            r"slug ~ '^[a-z0-9][a-z0-9-]{1,37}[a-z0-9]$'",
            name="ck_profiles_slug_format",
        ),
        *(_text_check(column, limit) for column, limit in PROFILE_TEXT_LIMITS.items()),
        CheckConstraint(
            "status <> 'PUBLISHED' OR (display_name IS NOT NULL AND headline IS NOT NULL)",
            name="ck_profiles_published_complete",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(39), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    # mutable entity — see DATABASE_SCHEMA.md "timestamps on mutable entities"
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="profile")


# ADR-020: contacts of a profile. Value lengths (min, max) per type; the stored
# value is normalized (see app/profile/contacts.py).
CONTACT_VALUE_LIMITS: dict[str, tuple[int, int]] = {
    "EMAIL": (1, 254),
    "TELEGRAM": (5, 32),
    "LINKEDIN": (3, 100),
    "PHONE": (9, 16),
    "OTHER": (1, 2048),
}
CONTACT_TYPES: tuple[str, ...] = tuple(CONTACT_VALUE_LIMITS)
CONTACT_LABEL_MAX_LENGTH = 40
CONTACTS_PER_PROFILE = 7
OTHER_CONTACTS_PER_PROFILE = 3

_CONTACT_VALUE_CHECK = (
    "btrim(value) <> '' AND ("
    + " OR ".join(
        f"(type = '{kind}' AND char_length(value) BETWEEN {low} AND {high})"
        for kind, (low, high) in CONTACT_VALUE_LIMITS.items()
    )
    + ")"
)


class ProfileContact(Base):
    __tablename__ = "profile_contacts"
    __table_args__ = (
        CheckConstraint(
            "type IN (" + ", ".join(f"'{kind}'" for kind in CONTACT_TYPES) + ")",
            name="ck_profile_contacts_type",
        ),
        CheckConstraint(_CONTACT_VALUE_CHECK, name="ck_profile_contacts_value"),
        # A name for OTHER only.
        CheckConstraint(
            "(type = 'OTHER') = (label IS NOT NULL)", name="ck_profile_contacts_label_presence"
        ),
        CheckConstraint(
            f"label IS NULL OR (char_length(label) <= {CONTACT_LABEL_MAX_LENGTH} "
            "AND btrim(label) <> '')",
            name="ck_profile_contacts_label",
        ),
        # With the position range this caps a profile at 7 contacts.
        UniqueConstraint("profile_id", "position", name="uq_profile_contacts_position"),
        CheckConstraint(
            f"position BETWEEN 1 AND {CONTACTS_PER_PROFILE}", name="ck_profile_contacts_position"
        ),
        # One standard contact of each type; the 3 OTHER are a domain rule only.
        Index(
            "uq_profile_contacts_type",
            "profile_id",
            "type",
            unique=True,
            postgresql_where=text("type <> 'OTHER'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    user: Mapped["User"] = relationship(back_populates="auth_sessions")
