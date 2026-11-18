"""project_screenshots

Revision ID: d5e9b3a7f204
Revises: c4d8a2f6e913
Create Date: 2026-11-18 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5e9b3a7f204"
down_revision: str | None = "c4d8a2f6e913"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ADR-0022: at most six screenshots per project; files live in the media volume.
    op.create_table(
        "project_screenshots",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("width", sa.SmallInteger(), nullable=False),
        sa.Column("height", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("position BETWEEN 1 AND 6", name="ck_project_screenshots_position"),
        sa.CheckConstraint(
            "char_length(caption) <= 200 AND btrim(caption) <> ''",
            name="ck_project_screenshots_caption",
        ),
        sa.CheckConstraint(
            "width BETWEEN 1 AND 2560 AND height BETWEEN 1 AND 2560",
            name="ck_project_screenshots_size",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "position",
            deferrable=True,
            initially="IMMEDIATE",
            name="uq_project_screenshots_position",
        ),
        sa.UniqueConstraint("storage_key"),
    )


def downgrade() -> None:
    op.drop_table("project_screenshots")
