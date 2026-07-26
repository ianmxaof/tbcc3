"""listening_relay_post_log — relay post history for dashboard

Revision ID: 100_listening_relay_post_log
Revises: 099_listening_relay_random_network
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "100_listening_relay_post_log"
down_revision: Union[str, None] = "099_relay_random_net"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "listening_relay_post_log" in insp.get_table_names():
        return
    op.create_table(
        "listening_relay_post_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("trigger_kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("source_label", sa.String(length=64), nullable=True),
        sa.Column("artist", sa.String(length=512), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("album", sa.String(length=512), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("message_thread_id", sa.Integer(), nullable=True),
        sa.Column("random_lane", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("template_slot", sa.Integer(), nullable=True),
        sa.Column("template_slots_total", sa.Integer(), nullable=True),
        sa.Column("ascii_beat", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("tryptych", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("copy_followups_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("send_silent", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("main_html_preview", sa.Text(), nullable=True),
        sa.Column("telegram_message_id", sa.Integer(), nullable=True),
        sa.Column("buffer_sent", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("discord_sent", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("extra_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("listening_relay_post_log")
