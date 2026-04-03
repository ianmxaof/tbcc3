"""Initial TBCC tables

Revision ID: 001
Revises:
Create Date: 2025-03-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "media",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_message_id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.String(), nullable=False),
        sa.Column("file_unique_id", sa.String(), nullable=False),
        sa.Column("media_type", sa.String(), nullable=True),
        sa.Column("source_channel", sa.String(), nullable=True),
        sa.Column("tags", sa.String(), nullable=True),
        sa.Column("pool_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), server_default="pending", nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_unique_id"),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=True),
        sa.Column("identifier", sa.String(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=True),
        sa.Column("pool_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "content_pools",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("album_size", sa.Integer(), server_default="5", nullable=True),
        sa.Column("interval_minutes", sa.Integer(), server_default="60", nullable=True),
        sa.Column("last_posted", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "bots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("api_id", sa.String(), nullable=True),
        sa.Column("api_hash", sa.String(), nullable=True),
        sa.Column("session", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("status", sa.String(), server_default="stopped", nullable=True),
        sa.Column("last_seen", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.Integer(), nullable=True),
        sa.Column("plan", sa.String(), nullable=True),
        sa.Column("status", sa.String(), server_default="active", nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("payment_method", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("subscriptions")
    op.drop_table("bots")
    op.drop_table("content_pools")
    op.drop_table("sources")
    op.drop_table("media")
