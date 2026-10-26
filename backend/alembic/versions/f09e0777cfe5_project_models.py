"""project_models

Revision ID: f09e0777cfe5
Revises: a3f1c9e27b54
Create Date: 2026-10-26 21:14:23.259575

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f09e0777cfe5"
down_revision: str | None = "a3f1c9e27b54"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Copied, not imported: a migration must not change when the model changes later.
_PROJECT_TEXT_LIMITS = {
    "title": 100,
    "summary": 300,
    "description": 5000,
    "problem": 2000,
    "results": 2000,
    "role": 100,
    "contribution": 2000,
}


def _uuid_pk() -> sa.Column:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False)


def upgrade() -> None:
    # ADR-015: shared technologies, unique ignoring case.
    op.create_table(
        "technologies",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "char_length(name) <= 50 AND btrim(name) <> ''", name="ck_technologies_name"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_technologies_name_lower",
        "technologies",
        [sa.literal_column("lower(name)")],
        unique=True,
    )

    op.create_table(
        "projects",
        _uuid_pk(),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="DRAFT", nullable=False),
        sa.Column("visibility", sa.String(length=20), server_default="PRIVATE", nullable=False),
        *(sa.Column(column, sa.Text(), nullable=True) for column in _PROJECT_TEXT_LIMITS),
        _created_at(),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "(status, visibility) IN (('DRAFT', 'PRIVATE'), ('PUBLISHED', 'PUBLIC'), "
            "('PUBLISHED', 'PRIVATE'), ('ARCHIVED', 'PRIVATE'))",
            name="ck_projects_state",
        ),
        *(
            sa.CheckConstraint(
                f"char_length({column}) <= {max_length} AND btrim({column}) <> ''",
                name=f"ck_projects_{column}",
            )
            for column, max_length in _PROJECT_TEXT_LIMITS.items()
        ),
        sa.CheckConstraint(
            "status <> 'PUBLISHED' OR (title IS NOT NULL AND summary IS NOT NULL "
            "AND role IS NOT NULL AND contribution IS NOT NULL)",
            name="ck_projects_published_complete",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"], unique=False)

    # A row means the project is featured. The position range with the deferrable
    # unique constraint caps a profile at three and allows a reorder in one UPDATE.
    op.create_table(
        "project_showcases",
        _uuid_pk(),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        _created_at(),
        sa.CheckConstraint("position BETWEEN 1 AND 3", name="ck_project_showcases_position"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_id",
            "position",
            deferrable=True,
            initially="IMMEDIATE",
            name="uq_project_showcases_position",
        ),
        sa.UniqueConstraint("project_id"),
    )

    op.create_table(
        "project_technologies",
        _uuid_pk(),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("technology_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("position BETWEEN 1 AND 20", name="ck_project_technologies_position"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["technology_id"], ["technologies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "position", name="uq_project_technologies_position"),
        sa.UniqueConstraint(
            "project_id", "technology_id", name="uq_project_technologies_technology"
        ),
    )


def downgrade() -> None:
    op.drop_table("project_technologies")
    op.drop_table("project_showcases")
    op.drop_index("ix_projects_owner_id", table_name="projects")
    op.drop_table("projects")
    op.drop_index("uq_technologies_name_lower", table_name="technologies")
    op.drop_table("technologies")
