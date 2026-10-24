"""profile_fields_and_avatar

Revision ID: a3f1c9e27b54
Revises: 198d5799de28
Create Date: 2026-10-24 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a3f1c9e27b54'
down_revision: str | None = '198d5799de28'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Copied, not imported: a migration must not change when the model changes later.
_TEXT_LIMITS = {
    "display_name": 100,
    "headline": 160,
    "bio": 2000,
    "location": 100,
}


def upgrade() -> None:
    for column in _TEXT_LIMITS:
        op.add_column('profiles', sa.Column(column, sa.Text(), nullable=True))
    for column, max_length in _TEXT_LIMITS.items():
        op.create_check_constraint(
            f'ck_profiles_{column}',
            'profiles',
            f"char_length({column}) <= {max_length} AND btrim({column}) <> ''",
        )
    op.create_check_constraint(
        'ck_profiles_published_complete',
        'profiles',
        "status <> 'PUBLISHED' OR (display_name IS NOT NULL AND headline IS NOT NULL)",
    )
    op.add_column(
        'github_accounts', sa.Column('avatar_url', sa.String(length=2048), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('github_accounts', 'avatar_url')
    op.drop_constraint('ck_profiles_published_complete', 'profiles', type_='check')
    for column in reversed(list(_TEXT_LIMITS)):
        op.drop_constraint(f'ck_profiles_{column}', 'profiles', type_='check')
        op.drop_column('profiles', column)
