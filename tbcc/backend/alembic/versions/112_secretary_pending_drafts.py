"""secretary_pending_drafts — DB-backed HITL draft queue (Pilot mode) survives restart

Revision ID: 112_secretary_pending_drafts
Revises: 111_secretary_bot_instances
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "112_secretary_pending_drafts"
down_revision: Union[str, None] = "111_secretary_bot_instances"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = set(insp.get_table_names())
    if "secretary_pending_drafts" in names:
        return
    op.create_table(
        "secretary_pending_drafts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("draft_id", sa.String(length=16), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("business_connection_id", sa.String(length=128), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("who", sa.String(length=128), nullable=True),
        sa.Column("customer_preview", sa.Text(), nullable=True),
        sa.Column("reply_text", sa.Text(), nullable=False),
        sa.Column("llm_messages_json", sa.Text(), nullable=True),
        sa.Column("extra_system_suffix", sa.Text(), nullable=True),
        sa.Column("coach_hint", sa.String(length=256), nullable=True),
        sa.Column("reply_mode", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_secretary_pending_drafts_draft_id",
        "secretary_pending_drafts",
        ["draft_id"],
        unique=True,
    )
    op.create_index(
        "ix_secretary_pending_drafts_user_id",
        "secretary_pending_drafts",
        ["user_id"],
    )
    op.create_index(
        "ix_secretary_pending_drafts_created_at",
        "secretary_pending_drafts",
        ["created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = set(insp.get_table_names())
    if "secretary_pending_drafts" not in names:
        return
    op.drop_index("ix_secretary_pending_drafts_created_at", table_name="secretary_pending_drafts")
    op.drop_index("ix_secretary_pending_drafts_user_id", table_name="secretary_pending_drafts")
    op.drop_index("ix_secretary_pending_drafts_draft_id", table_name="secretary_pending_drafts")
    op.drop_table("secretary_pending_drafts")
