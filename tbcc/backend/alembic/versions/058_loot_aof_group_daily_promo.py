"""Loot overseer: main AOF group chat + daily promo cron fields

Revision ID: 058_loot_aof_daily
Revises: 057_capture_archive
Create Date: 2026-05-23

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "058_loot_aof_daily"
down_revision: Union[str, None] = "057_capture_archive"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("loot_bot_settings", sa.Column("aof_group_chat_id", sa.BigInteger(), nullable=True))
    op.add_column("loot_bot_settings", sa.Column("aof_group_message_thread_id", sa.Integer(), nullable=True))
    op.add_column(
        "loot_bot_settings",
        sa.Column("daily_promo_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("loot_bot_settings", sa.Column("daily_promo_hour_utc", sa.Integer(), nullable=True))
    op.add_column("loot_bot_settings", sa.Column("daily_promo_intro_html", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("loot_bot_settings", "daily_promo_intro_html")
    op.drop_column("loot_bot_settings", "daily_promo_hour_utc")
    op.drop_column("loot_bot_settings", "daily_promo_enabled")
    op.drop_column("loot_bot_settings", "aof_group_message_thread_id")
    op.drop_column("loot_bot_settings", "aof_group_chat_id")
