"""conversion_playbooks

Revision ID: 117_conversion_playbooks
Revises: 116_add_userbot_outreach_tables
Create Date: 2026-08-17

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "117_conversion_playbooks"
down_revision: Union[str, None] = "116_add_userbot_outreach_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversion_playbooks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("phase_trajectory", sa.Text(), nullable=True),
        sa.Column("psych_markers_at_conversion", sa.Text(), nullable=True),
        sa.Column("message_count_at_conversion", sa.Integer(), nullable=True),
        sa.Column("payment_lane_used", sa.String(length=16), nullable=True),
        sa.Column("behavioral_directive_at_conversion", sa.String(length=512), nullable=True),
        sa.Column("conversion_outcome", sa.String(length=32), nullable=True),
        sa.Column("format_summary", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("times_matched", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_conversion_playbooks_telegram_user_id",
        "conversion_playbooks",
        ["telegram_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversion_playbooks_telegram_user_id", table_name="conversion_playbooks")
    op.drop_table("conversion_playbooks")