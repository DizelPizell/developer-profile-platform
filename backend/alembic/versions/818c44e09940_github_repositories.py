"""github_repositories

Revision ID: 818c44e09940
Revises: f09e0777cfe5
Create Date: 2026-10-30 14:29:13.553767

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "818c44e09940"
down_revision: str | None = "f09e0777cfe5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False)


def upgrade() -> None:
    # ADR-017: one row per GitHub repository, shared by every user who links it.
    # V1 stores metadata and languages only (ADR-018); no sync status here (ADR-009).
    op.create_table(
        "github_repositories",
        _uuid_pk(),
        sa.Column("github_repo_id", sa.BigInteger(), nullable=False),
        sa.Column("owner_github_id", sa.BigInteger(), nullable=False),
        sa.Column("owner_login", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("html_url", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_fork", sa.Boolean(), nullable=False),
        sa.Column("parent_full_name", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("pushed_at", sa.DateTime(), nullable=True),
        sa.Column("languages", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("unavailable_since", sa.DateTime(), nullable=True),
        _created_at(),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "btrim(owner_login) <> '' AND btrim(name) <> ''", name="ck_github_repositories_names"
        ),
        sa.CheckConstraint(
            "full_name = owner_login || '/' || name", name="ck_github_repositories_full_name"
        ),
        sa.CheckConstraint(
            "starts_with(html_url, 'https://github.com/')", name="ck_github_repositories_html_url"
        ),
        sa.CheckConstraint(
            "languages IS NULL OR jsonb_typeof(languages) = 'object'",
            name="ck_github_repositories_languages",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("github_repo_id"),
    )

    # Target of the composite foreign key below: it keeps project_repositories.owner_id
    # equal to the project's owner.
    op.create_unique_constraint("uq_projects_id_owner", "projects", ["id", "owner_id"])

    # One repository per project; a user links a repository to at most one of their
    # projects (ADR-017). Deleting a project removes its link; a linked repository
    # row cannot be deleted.
    op.create_table(
        "project_repositories",
        _uuid_pk(),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("github_repository_id", sa.UUID(), nullable=False),
        sa.Column("relation", sa.String(length=20), nullable=False),
        sa.Column(
            "relation_checked_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        _created_at(),
        sa.CheckConstraint(
            "relation IN ('OWNER', 'CONTRIBUTOR', 'NONE')", name="ck_project_repositories_relation"
        ),
        sa.ForeignKeyConstraint(
            ["github_repository_id"], ["github_repositories.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "owner_id"], ["projects.id", "projects.owner_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id", "github_repository_id", name="uq_project_repositories_owner_repository"
        ),
        sa.UniqueConstraint("project_id"),
    )
    op.create_index(
        "ix_project_repositories_github_repository_id",
        "project_repositories",
        ["github_repository_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_project_repositories_github_repository_id", table_name="project_repositories")
    op.drop_table("project_repositories")
    op.drop_constraint("uq_projects_id_owner", "projects", type_="unique")
    op.drop_table("github_repositories")
