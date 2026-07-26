"""goblin_drop + goblin_claim + listening_relay goblin settings

Revision ID: 101_goblin_drops
Revises: 100_listening_relay_post_log
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "101_goblin_drops"
down_revision: Union[str, None] = "100_listening_relay_post_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = set(insp.get_table_names())

    if "goblin_drop" not in names:
        op.create_table(
            "goblin_drop",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("token", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
            sa.Column("claims_used", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("claims_cap", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("relay_log_id", sa.Integer(), nullable=True),
            sa.Column("channel_id", sa.Integer(), nullable=True),
            sa.Column("message_thread_id", sa.Integer(), nullable=True),
            sa.Column("announce_message_id", sa.Integer(), nullable=True),
            sa.Column("announced_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("extra_json", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token"),
        )
        op.create_index("ix_goblin_drop_token", "goblin_drop", ["token"], unique=True)

    if "goblin_claim" not in names:
        op.create_table(
            "goblin_claim",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("drop_id", sa.Integer(), nullable=False),
            sa.Column("telegram_user_id", sa.Integer(), nullable=False),
            sa.Column("claimed_at", sa.DateTime(), nullable=False),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["drop_id"], ["goblin_drop.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_goblin_claim_drop_id", "goblin_claim", ["drop_id"])
        op.create_index("ix_goblin_claim_telegram_user_id", "goblin_claim", ["telegram_user_id"])

    if "listening_relay_settings" in names:
        cols = {c["name"] for c in insp.get_columns("listening_relay_settings")}
        additions = {
            "goblin_mode_enabled": sa.Column("goblin_mode_enabled", sa.Boolean(), nullable=False, server_default="0"),
            "goblin_spawn_chance": sa.Column("goblin_spawn_chance", sa.Float(), nullable=False, server_default="0.2"),
            "goblin_cooldown_minutes": sa.Column("goblin_cooldown_minutes", sa.Integer(), nullable=False, server_default="120"),
            "goblin_last_spawn_at": sa.Column("goblin_last_spawn_at", sa.DateTime(), nullable=True),
            "goblin_announce_ttl_seconds": sa.Column("goblin_announce_ttl_seconds", sa.Integer(), nullable=False, server_default="45"),
            "goblin_claims_cap": sa.Column("goblin_claims_cap", sa.Integer(), nullable=False, server_default="5"),
            "goblin_max_per_day_utc": sa.Column("goblin_max_per_day_utc", sa.Integer(), nullable=False, server_default="3"),
            "goblin_utc_day": sa.Column("goblin_utc_day", sa.String(length=10), nullable=True),
            "goblin_spawns_today": sa.Column("goblin_spawns_today", sa.Integer(), nullable=False, server_default="0"),
        }
        for col, ddl in additions.items():
            if col not in cols:
                op.add_column("listening_relay_settings", ddl)


def downgrade() -> None:
    op.drop_table("goblin_claim")
    op.drop_table("goblin_drop")
    for col in (
        "goblin_mode_enabled",
        "goblin_spawn_chance",
        "goblin_cooldown_minutes",
        "goblin_last_spawn_at",
        "goblin_announce_ttl_seconds",
        "goblin_claims_cap",
        "goblin_max_per_day_utc",
        "goblin_utc_day",
        "goblin_spawns_today",
    ):
        try:
            op.drop_column("listening_relay_settings", col)
        except Exception:
            pass
