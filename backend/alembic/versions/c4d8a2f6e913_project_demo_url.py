"""project_demo_url

Revision ID: c4d8a2f6e913
Revises: b7e2d4c81a3f
Create Date: 2026-11-17 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d8a2f6e913"
down_revision: str | None = "b7e2d4c81a3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ADR-0023: the demo is a link; the API checks it fully, the database only coarsely.
    op.add_column("projects", sa.Column("demo_url", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_projects_demo_url",
        "projects",
        "char_length(demo_url) <= 2048 AND demo_url ~ '^https?://'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_projects_demo_url", "projects", type_="check")
    op.drop_column("projects", "demo_url")
