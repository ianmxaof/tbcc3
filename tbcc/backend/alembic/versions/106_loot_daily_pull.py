"""Daily micro-pull + streak counters on loot_player_stats."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "106_loot_daily_pull"
down_revision: Union[str, None] = "105_income_traffic_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = set(insp.get_table_names())
    if "loot_player_stats" not in names:
        return

    cols = {c["name"] for c in insp.get_columns("loot_player_stats")}
    if "daily_pull_at" not in cols:
        op.add_column("loot_player_stats", sa.Column("daily_pull_at", sa.DateTime(), nullable=True))
    if "daily_streak_days" not in cols:
        op.add_column(
            "loot_player_stats",
            sa.Column("daily_streak_days", sa.Integer(), nullable=False, server_default="0"),
        )
    if "daily_streak_best" not in cols:
        op.add_column(
            "loot_player_stats",
            sa.Column("daily_streak_best", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = set(insp.get_table_names())
    if "loot_player_stats" not in names:
        return

    cols = {c["name"] for c in insp.get_columns("loot_player_stats")}
    for col in ("daily_streak_best", "daily_streak_days", "daily_pull_at"):
        if col in cols:
            op.drop_column("loot_player_stats", col)
