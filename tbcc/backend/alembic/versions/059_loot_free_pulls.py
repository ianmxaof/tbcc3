"""Loot: free_pulls_used on loot_player_stats (max 5 nerfed DM pulls per user)

Revision ID: 059_loot_free_pulls
Revises: 058_loot_aof_daily
Create Date: 2026-05-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "059_loot_free_pulls"
down_revision: Union[str, None] = "058_loot_aof_daily"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "loot_player_stats",
        sa.Column("free_pulls_used", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("loot_player_stats", "free_pulls_used")
