"""growth_settings: dashboard overrides for referrals + landing bulletin

Revision ID: 018_growth_settings
Revises: 017_scheduled_forum_topic
Create Date: 2025-03-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "018_growth_settings"
down_revision: Union[str, None] = "017_scheduled_forum_topic"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "growth_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("landing_bulletin_chat_id", sa.String(length=256), nullable=True),
        sa.Column("landing_bulletin_message_thread_id", sa.Integer(), nullable=True),
        sa.Column("landing_bulletin_hour_utc", sa.Integer(), nullable=True),
        sa.Column("landing_bulletin_bot_username", sa.String(length=128), nullable=True),
        sa.Column("landing_bulletin_intro", sa.Text(), nullable=True),
        sa.Column("referral_group_invite_link", sa.String(length=512), nullable=True),
        sa.Column("referral_group_name", sa.String(length=256), nullable=True),
        sa.Column("referral_reward_days", sa.Integer(), nullable=True),
        sa.Column("referral_mode", sa.String(length=32), nullable=True),
        sa.Column("milestone_progress_chat_id", sa.String(length=256), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "INSERT INTO growth_settings (id) VALUES (1)"
    )


def downgrade() -> None:
    op.drop_table("growth_settings")
