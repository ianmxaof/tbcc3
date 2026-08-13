"""secretary_bot_instances — inbound clone fleet registry (Phase 2)

Revision ID: 111_secretary_bot_instances
Revises: 110_secretary_reply_mode
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "111_secretary_bot_instances"
down_revision: Union[str, None] = "110_secretary_reply_mode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = set(insp.get_table_names())
    if "secretary_bot_instances" in names:
        return
    op.create_table(
        "secretary_bot_instances",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("bot_username", sa.String(length=64), nullable=True),
        sa.Column("bot_token", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notify_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_secretary_bot_instances_username", "secretary_bot_instances", ["bot_username"])
    op.create_index("ix_secretary_bot_instances_active", "secretary_bot_instances", ["is_active"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = set(insp.get_table_names())
    if "secretary_bot_instances" not in names:
        return
    op.drop_index("ix_secretary_bot_instances_active", table_name="secretary_bot_instances")
    op.drop_index("ix_secretary_bot_instances_username", table_name="secretary_bot_instances")
    op.drop_table("secretary_bot_instances")
