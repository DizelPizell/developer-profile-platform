"""profile_contacts

Revision ID: b7e2d4c81a3f
Revises: 9cef1f7367c5
Create Date: 2026-11-10 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2d4c81a3f"
down_revision: str | None = "9cef1f7367c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy of the limits in app/models/identity.py at this revision.
_VALUE_LIMITS = {
    "EMAIL": (1, 254),
    "TELEGRAM": (5, 32),
    "LINKEDIN": (3, 100),
    "PHONE": (9, 16),
    "OTHER": (1, 2048),
}


def upgrade() -> None:
    # ADR-020: contacts of a profile, replaced as a whole by PATCH /profile.
    value_check = (
        "btrim(value) <> '' AND ("
        + " OR ".join(
            f"(type = '{kind}' AND char_length(value) BETWEEN {low} AND {high})"
            for kind, (low, high) in _VALUE_LIMITS.items()
        )
        + ")"
    )
    op.create_table(
        "profile_contacts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "type IN ('EMAIL', 'TELEGRAM', 'LINKEDIN', 'PHONE', 'OTHER')",
            name="ck_profile_contacts_type",
        ),
        sa.CheckConstraint(value_check, name="ck_profile_contacts_value"),
        sa.CheckConstraint(
            "(type = 'OTHER') = (label IS NOT NULL)", name="ck_profile_contacts_label_presence"
        ),
        sa.CheckConstraint(
            "label IS NULL OR (char_length(label) <= 40 AND btrim(label) <> '')",
            name="ck_profile_contacts_label",
        ),
        sa.CheckConstraint("position BETWEEN 1 AND 7", name="ck_profile_contacts_position"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "position", name="uq_profile_contacts_position"),
    )
    op.create_index(
        "uq_profile_contacts_type",
        "profile_contacts",
        ["profile_id", "type"],
        unique=True,
        postgresql_where=sa.text("type <> 'OTHER'"),
    )


def downgrade() -> None:
    op.drop_index("uq_profile_contacts_type", table_name="profile_contacts")
    op.drop_table("profile_contacts")
