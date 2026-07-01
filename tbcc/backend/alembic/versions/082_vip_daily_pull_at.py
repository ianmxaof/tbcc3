"""loot_player_stats.vip_daily_pull_at for VIP daily god roll cooldown

Revision ID: 082_vip_daily_pull_at
Revises: 081_drop_countdown
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "082_vip_daily_pull_at"
down_revision: Union[str, None] = "081_drop_countdown"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("loot_player_stats", sa.Column("vip_daily_pull_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("loot_player_stats", "vip_daily_pull_at")
