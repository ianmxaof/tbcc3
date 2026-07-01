"""drop_countdown_sessions + feed rhythm support tables

Revision ID: 081_drop_countdown
Revises: 080_secretary_system_prompt
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "081_drop_countdown"
down_revision: Union[str, None] = "080_secretary_system_prompt"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "drop_countdown_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("channel_identifier", sa.String(256), nullable=False),
        sa.Column("message_thread_id", sa.Integer(), nullable=True),
        sa.Column("lane_key", sa.String(64), nullable=False),
        sa.Column("pool_id", sa.Integer(), nullable=True),
        sa.Column("scheduled_post_id", sa.Integer(), nullable=True),
        sa.Column("drop_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="scheduled"),
        sa.Column("countdown_chat_id", sa.String(64), nullable=True),
        sa.Column("countdown_message_id", sa.BigInteger(), nullable=True),
        sa.Column("last_tick_label", sa.String(32), nullable=True),
        sa.Column("error_note", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_drop_countdown_status_drop_at",
        "drop_countdown_sessions",
        ["status", "drop_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_drop_countdown_status_drop_at", table_name="drop_countdown_sessions")
    op.drop_table("drop_countdown_sessions")
