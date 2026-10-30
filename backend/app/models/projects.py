import uuid
from datetime import datetime

from sqlalchemy import (
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
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Lifecycle and visibility pairs allowed by ADR-015.
PROJECT_STATES: tuple[tuple[str, str], ...] = (
    ("DRAFT", "PRIVATE"),
    ("PUBLISHED", "PUBLIC"),
    ("PUBLISHED", "PRIVATE"),
    ("ARCHIVED", "PRIVATE"),
)

PROJECT_TEXT_LIMITS: dict[str, int] = {
    "title": 100,
    "summary": 300,
    "description": 5000,
    "problem": 2000,
    "results": 2000,
    "role": 100,
    "contribution": 2000,
}

# Text fields a PUBLISHED project must have; "at least one technology" is a
# domain rule, it lives in another table.
PROJECT_PUBLISH_REQUIRED: tuple[str, ...] = ("title", "summary", "role", "contribution")

TECHNOLOGY_NAME_MAX_LENGTH = 50
TECHNOLOGIES_PER_PROJECT = 20
FEATURED_PROJECTS_PER_PROFILE = 3


def _text_check(column: str, max_length: int) -> CheckConstraint:
    return CheckConstraint(
        f"char_length({column}) <= {max_length} AND btrim({column}) <> ''",
        name=f"ck_projects_{column}",
    )


_STATE_PAIRS = ", ".join(f"('{status}', '{visibility}')" for status, visibility in PROJECT_STATES)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(f"(status, visibility) IN ({_STATE_PAIRS})", name="ck_projects_state"),
        *(_text_check(column, limit) for column, limit in PROJECT_TEXT_LIMITS.items()),
        CheckConstraint(
            "status <> 'PUBLISHED' OR ("
            + " AND ".join(f"{column} IS NOT NULL" for column in PROJECT_PUBLISH_REQUIRED)
            + ")",
            name="ck_projects_published_complete",
        ),
        # Target of the composite foreign key from project_repositories (ADR-017).
        UniqueConstraint("id", "owner_id", name="uq_projects_id_owner"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), server_default="DRAFT", nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), server_default="PRIVATE", nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    results: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str | None] = mapped_column(Text, nullable=True)
    contribution: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    # mutable entity — see DATABASE_SCHEMA.md "timestamps on mutable entities"
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class Technology(Base):
    """Shared by all users; unique ignoring case, spelling of the first creator."""

    __tablename__ = "technologies"
    __table_args__ = (
        CheckConstraint(
            f"char_length(name) <= {TECHNOLOGY_NAME_MAX_LENGTH} AND btrim(name) <> ''",
            name="ck_technologies_name",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


Index("uq_technologies_name_lower", func.lower(Technology.name), unique=True)


class ProjectTechnology(Base):
    __tablename__ = "project_technologies"
    __table_args__ = (
        UniqueConstraint("project_id", "technology_id", name="uq_project_technologies_technology"),
        # With the position range this caps a project at 20 technologies.
        UniqueConstraint("project_id", "position", name="uq_project_technologies_position"),
        CheckConstraint(
            f"position BETWEEN 1 AND {TECHNOLOGIES_PER_PROJECT}",
            name="ck_project_technologies_position",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Technologies are never deleted in V1; RESTRICT keeps a used one from vanishing.
    technology_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("technologies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class ProjectShowcase(Base):
    """A row means the project is featured on its owner's profile (ADR-015)."""

    __tablename__ = "project_showcases"
    __table_args__ = (
        # With the position range this caps a profile at three featured projects.
        # Deferrable: checked at the end of each statement, so a reorder is one UPDATE.
        UniqueConstraint(
            "profile_id",
            "position",
            name="uq_project_showcases_position",
            deferrable=True,
            initially="IMMEDIATE",
        ),
        CheckConstraint(
            f"position BETWEEN 1 AND {FEATURED_PROJECTS_PER_PROFILE}",
            name="ck_project_showcases_position",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
