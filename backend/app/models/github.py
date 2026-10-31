import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
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

# Sync job states (ADR-009); a job with retries ahead is QUEUED, never FAILED.
SYNC_JOB_STATUSES: tuple[str, ...] = ("QUEUED", "SYNCING", "SYNCED", "FAILED")
ACTIVE_SYNC_JOB_STATUSES: tuple[str, ...] = ("QUEUED", "SYNCING")
# Categories synchronized in V1 (ADR-018).
SYNC_CATEGORIES: tuple[str, ...] = ("metadata", "languages")
# Errors are stored as fixed labels such as NOT_FOUND, never as GitHub's text.
SYNC_ERROR_PATTERN = "^[A-Z_]{1,64}$"


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


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
            _in("relation", REPOSITORY_RELATIONS), name="ck_project_repositories_relation"
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


class GitHubSyncJob(Base):
    """One logical sync request of a repository (ADR-009, ADR-018).

    The single source of truth for sync status. Retries reuse the row; a new row
    is created only for a new request. At most one active job per repository.
    """

    __tablename__ = "github_sync_jobs"
    __table_args__ = (
        CheckConstraint(_in("status", SYNC_JOB_STATUSES), name="ck_github_sync_jobs_status"),
        CheckConstraint("attempt_count >= 0", name="ck_github_sync_jobs_attempt_count"),
        CheckConstraint(
            f"last_error ~ '{SYNC_ERROR_PATTERN}'", name="ck_github_sync_jobs_last_error"
        ),
        # An enqueue is INSERT ... ON CONFLICT DO NOTHING against this index (ADR-018).
        Index(
            "uq_github_sync_jobs_active",
            "github_repository_id",
            unique=True,
            postgresql_where=text(_in("status", ACTIVE_SYNC_JOB_STATUSES)),
        ),
        # The worker's claim: due QUEUED jobs, oldest first, with SKIP LOCKED.
        Index(
            "ix_github_sync_jobs_claim",
            "scheduled_at",
            postgresql_where=text("status = 'QUEUED'"),
        ),
        # The latest job of a repository: its status, the manual pause and the
        # periodic schedule.
        Index("ix_github_sync_jobs_repository_created", "github_repository_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # CASCADE: only a repository no project links can be deleted, and its sync
    # records go with it.
    github_repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("github_repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), server_default="QUEUED", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    # Set on every status change; the watchdog finds a stale SYNCING job by it.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class GitHubSyncCategoryStatus(Base):
    """Freshness of one category of a repository, whatever the job outcome
    (ADR-011, ADR-018). One row per repository and category."""

    __tablename__ = "github_sync_category_status"
    __table_args__ = (
        UniqueConstraint(
            "github_repository_id",
            "category",
            name="uq_github_sync_category_status_repository_category",
        ),
        CheckConstraint(
            _in("category", SYNC_CATEGORIES), name="ck_github_sync_category_status_category"
        ),
        CheckConstraint(
            f"last_error ~ '{SYNC_ERROR_PATTERN}'",
            name="ck_github_sync_category_status_last_error",
        ),
        CheckConstraint(
            "(last_error IS NULL) = (last_error_at IS NULL)",
            name="ck_github_sync_category_status_error_time",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    github_repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("github_repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
