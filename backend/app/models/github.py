import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.github.constants import GITHUB_HTML_URL_PREFIX

# Relation of the developer to a linked repository, from GitHub data (ADR-017).
REPOSITORY_RELATIONS: tuple[str, ...] = ("OWNER", "CONTRIBUTOR", "NONE")


class GitHubRepository(Base):
    """One row per GitHub repository, shared by every user who links it (ADR-017).

    V1 stores metadata and languages only (ADR-018). Sync status and times live
    in the sync tables, not here (ADR-009).
    """

    __tablename__ = "github_repositories"
    __table_args__ = (
        CheckConstraint(
            "btrim(owner_login) <> '' AND btrim(name) <> ''",
            name="ck_github_repositories_names",
        ),
        CheckConstraint(
            "full_name = owner_login || '/' || name",
            name="ck_github_repositories_full_name",
        ),
        # Rendered as a link on public pages.
        CheckConstraint(
            f"starts_with(html_url, '{GITHUB_HTML_URL_PREFIX}')",
            name="ck_github_repositories_html_url",
        ),
        # GitHub's own shape: {"language": bytes}; ordering is done when read.
        CheckConstraint(
            "languages IS NULL OR jsonb_typeof(languages) = 'object'",
            name="ck_github_repositories_languages",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    github_repo_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    owner_github_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner_login: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    html_url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_fork: Mapped[bool] = mapped_column(Boolean, nullable=False)
    parent_full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    languages: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Set after two 404s in a row; a repository fact, not sync status (ADR-017, ADR-018).
    unavailable_since: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    # mutable entity — see DATABASE_SCHEMA.md "timestamps on mutable entities"
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class ProjectRepository(Base):
    """Links a project to its repository (ADR-017).

    owner_id repeats the project's owner so that the database holds "a user links
    a repository to at most one of their projects"; the composite foreign key keeps
    it equal to projects.owner_id.
    """

    __tablename__ = "project_repositories"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "owner_id"],
            ["projects.id", "projects.owner_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "owner_id", "github_repository_id", name="uq_project_repositories_owner_repository"
        ),
        CheckConstraint(
            "relation IN (" + ", ".join(f"'{value}'" for value in REPOSITORY_RELATIONS) + ")",
            name="ck_project_repositories_relation",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # RESTRICT: a linked repository row cannot be removed.
    github_repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("github_repositories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    relation: Mapped[str] = mapped_column(String(20), nullable=False)
    relation_checked_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
