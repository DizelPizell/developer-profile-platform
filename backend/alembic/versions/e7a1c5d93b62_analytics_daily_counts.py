"""analytics_daily_counts

Revision ID: e7a1c5d93b62
Revises: d5e9b3a7f204
Create Date: 2026-11-20 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7a1c5d93b62"
down_revision: str | None = "d5e9b3a7f204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ADR-0029: daily counters of events, nothing about the visitor.
    op.create_table(
        "analytics_daily_counts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('PROFILE_VIEW', 'PROJECT_VIEW', 'DEMO_CLICK', 'GITHUB_CLICK', "
            "'CONTACT_CLICK')",
            name="ck_analytics_event_type",
        ),
        sa.CheckConstraint(
            "(event_type NOT IN ('PROJECT_VIEW', 'DEMO_CLICK') OR project_id IS NOT NULL) "
            "AND (event_type NOT IN ('PROFILE_VIEW', 'CONTACT_CLICK') OR project_id IS NULL)",
            name="ck_analytics_project",
        ),
        sa.CheckConstraint("count > 0", name="ck_analytics_count"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_id",
            "project_id",
            "event_type",
            "day",
            name="uq_analytics_daily_counts",
            postgresql_nulls_not_distinct=True,
        ),
    )
    # The unique index leads with profile_id; project_id needs its own for the cascade.
    op.create_index(
        "ix_analytics_daily_counts_project_id", "analytics_daily_counts", ["project_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_daily_counts_project_id", table_name="analytics_daily_counts")
    op.drop_table("analytics_daily_counts")
