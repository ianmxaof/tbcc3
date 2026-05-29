"""Loot player stats + modifier min_rarity_tier."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "052_loot_tier_player_stats"
down_revision: Union[str, None] = "051_custom_emoji_presets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "loot_player_stats",
        sa.Column("telegram_user_id", sa.BigInteger(), primary_key=True),
        sa.Column("roll_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_roll_at", sa.DateTime(), nullable=True),
        sa.Column("last_roll_at", sa.DateTime(), nullable=True),
    )
    with op.batch_alter_table("loot_modifiers") as batch_op:
        batch_op.add_column(sa.Column("min_rarity_tier", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("loot_modifiers") as batch_op:
        batch_op.drop_column("min_rarity_tier")
    op.drop_table("loot_player_stats")
