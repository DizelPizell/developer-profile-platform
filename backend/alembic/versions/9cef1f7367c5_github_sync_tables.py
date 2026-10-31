"""github_sync_tables

Revision ID: 9cef1f7367c5
Revises: 818c44e09940
Create Date: 2026-10-31 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9cef1f7367c5"
down_revision: str | None = "818c44e09940"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Errors are fixed labels such as NOT_FOUND, never GitHub's text.
_ERROR_LABEL = "last_error ~ '^[A-Z_]{1,64}$'"


def _uuid_pk() -> sa.Column:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _repository_fk() -> sa.ForeignKeyConstraint:
    # Only a repository no project links can be deleted; its sync records go with it.
    return sa.ForeignKeyConstraint(
        ["github_repository_id"], ["github_repositories.id"], ondelete="CASCADE"
    )


def upgrade() -> None:
    # ADR-009, ADR-018: one row per logical sync request, the only place for sync
    # status. Existing links get no rows: no job means NOT_SYNCED.
    op.create_table(
        "github_sync_jobs",
        _uuid_pk(),
        sa.Column("github_repository_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="QUEUED", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'SYNCING', 'SYNCED', 'FAILED')",
            name="ck_github_sync_jobs_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_github_sync_jobs_attempt_count"),
        sa.CheckConstraint(_ERROR_LABEL, name="ck_github_sync_jobs_last_error"),
        _repository_fk(),
        sa.PrimaryKeyConstraint("id"),
    )
    # At most one active job per repository; an enqueue is ON CONFLICT DO NOTHING.
    op.create_index(
        "uq_github_sync_jobs_active",
        "github_sync_jobs",
        ["github_repository_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'SYNCING')"),
    )
    # The worker's claim: due QUEUED jobs, oldest first.
    op.create_index(
        "ix_github_sync_jobs_claim",
        "github_sync_jobs",
        ["scheduled_at"],
        unique=False,
        postgresql_where=sa.text("status = 'QUEUED'"),
    )
    # The latest job of a repository: status, manual pause, periodic schedule.
    op.create_index(
        "ix_github_sync_jobs_repository_created",
        "github_sync_jobs",
        ["github_repository_id", "created_at"],
        unique=False,
    )

    # ADR-011, ADR-018: freshness per repository and category (metadata, languages).
    op.create_table(
        "github_sync_category_status",
        _uuid_pk(),
        sa.Column("github_repository_id", sa.UUID(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "category IN ('metadata', 'languages')",
            name="ck_github_sync_category_status_category",
        ),
        sa.CheckConstraint(_ERROR_LABEL, name="ck_github_sync_category_status_last_error"),
        sa.CheckConstraint(
            "(last_error IS NULL) = (last_error_at IS NULL)",
            name="ck_github_sync_category_status_error_time",
        ),
        _repository_fk(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "github_repository_id",
            "category",
            name="uq_github_sync_category_status_repository_category",
        ),
    )


def downgrade() -> None:
    op.drop_table("github_sync_category_status")
    op.drop_index("ix_github_sync_jobs_repository_created", table_name="github_sync_jobs")
    op.drop_index("ix_github_sync_jobs_claim", table_name="github_sync_jobs")
    op.drop_index("uq_github_sync_jobs_active", table_name="github_sync_jobs")
    op.drop_table("github_sync_jobs")
