"""listening relay: optional <pre> copy block (follow-up message below Last.fm preview)

Revision ID: 053_listening_relay_copy_block
Revises: 052_loot_tier_player_stats
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "053_listening_relay_copy_block"
down_revision: Union[str, None] = "052_loot_tier_player_stats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "listening_relay_settings" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("listening_relay_settings")}
    if "message_copy_block_variations" not in cols:
        op.add_column(
            "listening_relay_settings",
            sa.Column("message_copy_block_variations", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "listening_relay_settings" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("listening_relay_settings")}
    if "message_copy_block_variations" in cols:
        op.drop_column("listening_relay_settings", "message_copy_block_variations")
