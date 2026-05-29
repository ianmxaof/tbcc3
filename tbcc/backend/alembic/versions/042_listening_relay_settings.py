"""listening_relay_settings single-row table

Revision ID: 042_listening_relay_settings
Revises: 041_caption_snippets
Create Date: 2026-05-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "042_listening_relay_settings"
down_revision: Union[str, None] = "041_caption_snippets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "listening_relay_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("message_thread_id", sa.Integer(), nullable=True),
        sa.Column("lastfm_username", sa.String(length=256), nullable=True),
        sa.Column("lastfm_api_key", sa.String(length=128), nullable=True),
        sa.Column("poll_interval_minutes", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_poll_at", sa.DateTime(), nullable=True),
        sa.Column("last_lastfm_signature", sa.String(length=512), nullable=True),
        sa.Column("message_template_html", sa.Text(), nullable=True),
        sa.Column("webhook_secret", sa.String(length=128), nullable=True),
        sa.Column("last_webhook_signature", sa.String(length=512), nullable=True),
        sa.Column("send_silent", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("listening_relay_settings")
