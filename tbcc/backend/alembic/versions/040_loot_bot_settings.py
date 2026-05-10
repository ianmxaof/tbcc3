"""Loot overseer bot settings (singleton row for dashboard + bots.loot_bot)

Revision ID: 040_loot_bot_settings
Revises: 039_loot_room
Create Date: 2026-05-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "040_loot_bot_settings"
down_revision: Union[str, None] = "039_loot_room"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "loot_bot_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bot_token", sa.Text(), nullable=True),
        sa.Column("bot_username", sa.String(length=64), nullable=True),
        sa.Column("primary_loot_room_invite_url", sa.Text(), nullable=True),
        sa.Column("primary_loot_room_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("config_poll_seconds", sa.Integer(), nullable=True),
        sa.Column("narrative_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("narrative_system_prompt", sa.Text(), nullable=True),
        sa.Column("drop_spoiler_default", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("runtime_adapter", sa.String(length=32), nullable=True),
        sa.Column("runtime_cmd_start", sa.Text(), nullable=True),
        sa.Column("runtime_cmd_stop", sa.Text(), nullable=True),
        sa.Column("runtime_cmd_restart", sa.Text(), nullable=True),
        sa.Column("runtime_cmd_reload", sa.Text(), nullable=True),
        sa.Column("runtime_cmd_status", sa.Text(), nullable=True),
        sa.Column("operator_notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO loot_bot_settings (
              id, bot_token, bot_username, primary_loot_room_invite_url,
              narrative_enabled, drop_spoiler_default
            ) VALUES (
              1, NULL, 'aof_lootgod_bot', 'https://t.me/+97f4Crv3G1RkMGU5',
              false, true
            )
            """
        )
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "SELECT setval(pg_get_serial_sequence('loot_bot_settings', 'id'), "
                "(SELECT COALESCE(MAX(id), 1) FROM loot_bot_settings))"
            )
        )


def downgrade() -> None:
    op.drop_table("loot_bot_settings")
