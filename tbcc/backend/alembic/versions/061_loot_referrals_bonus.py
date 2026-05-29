"""Loot referrals (bonus free pulls) + overseer referral settings."""

from alembic import op
import sqlalchemy as sa

revision = "061_loot_referrals_bonus"
down_revision = "060_loot_buffer_mirror"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "loot_player_stats",
        sa.Column("bonus_free_pulls", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "loot_referral_tracking",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("referred_user_id", sa.BigInteger(), nullable=False),
        sa.Column("referrer_user_id", sa.BigInteger(), nullable=False),
        sa.Column("credited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("referred_user_id", name="uq_loot_referral_referred"),
    )
    op.create_index("ix_loot_referral_referrer", "loot_referral_tracking", ["referrer_user_id"])
    op.add_column(
        "loot_bot_settings",
        sa.Column("loot_referral_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "loot_bot_settings",
        sa.Column("referral_bonus_pulls", sa.Integer(), nullable=True),
    )
    op.alter_column("loot_player_stats", "bonus_free_pulls", server_default=None)
    op.alter_column("loot_bot_settings", "loot_referral_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("loot_bot_settings", "referral_bonus_pulls")
    op.drop_column("loot_bot_settings", "loot_referral_enabled")
    op.drop_index("ix_loot_referral_referrer", table_name="loot_referral_tracking")
    op.drop_table("loot_referral_tracking")
    op.drop_column("loot_player_stats", "bonus_free_pulls")
