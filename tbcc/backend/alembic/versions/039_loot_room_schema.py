"""Loot room: pools eligibility, config, interval tiers, modifiers, sessions, drops, dedupe

Revision ID: 039_loot_room
Revises: 038_link_resolver
Create Date: 2026-05-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "039_loot_room"
down_revision: Union[str, None] = "038_link_resolver"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "loot_interval_tiers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("drop_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("bonus_album_draws", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rarity_shift", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "loot_game_config",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("p_modifier_slots_json", sa.Text(), nullable=False),
        sa.Column("tag_affinity_exponent", sa.Float(), nullable=False, server_default="1.35"),
        sa.Column("tag_weight_floor", sa.Float(), nullable=False, server_default="0.35"),
        sa.Column("tag_weight_ceiling", sa.Float(), nullable=False, server_default="3.5"),
        sa.Column("max_dup_media_per_session", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pity_steps_json", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "loot_pool_eligibility",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("content_pool_id", sa.Integer(), nullable=False),
        sa.Column("loot_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("min_rarity_tier", sa.Integer(), nullable=True),
        sa.Column("max_rarity_tier", sa.Integer(), nullable=True),
        sa.Column("base_weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.ForeignKeyConstraint(["content_pool_id"], ["content_pools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_pool_id", name="uq_loot_pool_eligibility_pool"),
    )

    op.create_table(
        "loot_modifiers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("label", sa.String(length=256), nullable=True),
        sa.Column("target_url", sa.Text(), nullable=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("weight_base", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("rarity_focus", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("bypass_vip", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "loot_modifier_tag_weights",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("modifier_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("multiplier", sa.Float(), nullable=False, server_default="1.5"),
        sa.ForeignKeyConstraint(["modifier_id"], ["loot_modifiers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tbcc_tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("modifier_id", "tag_id", name="uq_loot_modifier_tag_weight"),
    )

    op.create_table(
        "loot_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("interval_tier_id", sa.Integer(), nullable=False),
        sa.Column(
            "preference_tags_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "state",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("external_ref", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["interval_tier_id"], ["loot_interval_tiers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_loot_sessions_telegram_user_id", "loot_sessions", ["telegram_user_id"])

    op.create_table(
        "loot_drop_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(), nullable=False),
        sa.Column("rarity_tier", sa.Integer(), nullable=False),
        sa.Column("media_ids_json", sa.Text(), nullable=False),
        sa.Column(
            "modifier_ids_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("modifier_slot_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tag_bias_snapshot_json", sa.Text(), nullable=True),
        sa.Column(
            "delivery_status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("telegram_message_ids_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["loot_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_loot_drop_events_session_scheduled", "loot_drop_events", ["session_id", "scheduled_for"])

    op.create_table(
        "loot_player_media_seen",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("media_id", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["loot_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id", "media_id", name="uq_loot_player_media_seen"),
    )
    op.create_index("ix_loot_player_media_seen_user", "loot_player_media_seen", ["telegram_user_id"])

    op.create_table(
        "loot_player_modifier_seen",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("modifier_id", sa.Integer(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("seen_count", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["modifier_id"], ["loot_modifiers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id", "modifier_id", name="uq_loot_player_modifier_seen"),
    )
    op.create_index("ix_loot_player_modifier_seen_user", "loot_player_modifier_seen", ["telegram_user_id"])

    op.execute(
        sa.text(
            """
            INSERT INTO loot_interval_tiers (code, drop_interval_seconds, bonus_album_draws, rarity_shift)
            VALUES
              ('m60', 3600, 0, 0),
              ('m45', 2700, 0, 0),
              ('m30', 1800, 1, 0),
              ('m15', 900, 2, 1)
            """
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO loot_game_config (
              p_modifier_slots_json, tag_affinity_exponent, tag_weight_floor,
              tag_weight_ceiling, max_dup_media_per_session, pity_steps_json, updated_at
            ) VALUES (
              '[0.55,0.28,0.12,0.05]',
              1.35,
              0.35,
              3.5,
              0,
              NULL,
              CURRENT_TIMESTAMP
            )
            """
        )
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "SELECT setval(pg_get_serial_sequence('loot_interval_tiers', 'id'), "
                "(SELECT COALESCE(MAX(id), 1) FROM loot_interval_tiers))"
            )
        )
        op.execute(
            sa.text(
                "SELECT setval(pg_get_serial_sequence('loot_game_config', 'id'), "
                "(SELECT COALESCE(MAX(id), 1) FROM loot_game_config))"
            )
        )


def downgrade() -> None:
    op.drop_index("ix_loot_player_modifier_seen_user", table_name="loot_player_modifier_seen")
    op.drop_table("loot_player_modifier_seen")
    op.drop_index("ix_loot_player_media_seen_user", table_name="loot_player_media_seen")
    op.drop_table("loot_player_media_seen")
    op.drop_index("ix_loot_drop_events_session_scheduled", table_name="loot_drop_events")
    op.drop_table("loot_drop_events")
    op.drop_index("ix_loot_sessions_telegram_user_id", table_name="loot_sessions")
    op.drop_table("loot_sessions")
    op.drop_table("loot_modifier_tag_weights")
    op.drop_table("loot_modifiers")
    op.drop_table("loot_pool_eligibility")
    op.drop_table("loot_game_config")
    op.drop_table("loot_interval_tiers")
