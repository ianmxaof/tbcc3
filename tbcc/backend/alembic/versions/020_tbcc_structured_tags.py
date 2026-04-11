"""Structured tags (tbcc_tags + media_tag_links) for auto-tagging and filters

Revision ID: 020_tbcc_structured_tags
Revises: 019_channel_webhook_url
Create Date: 2026-04-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "020_tbcc_structured_tags"
down_revision: Union[str, None] = "019_channel_webhook_url"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tbcc_tags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tbcc_tags_slug", "tbcc_tags", ["slug"], unique=True)
    op.create_table(
        "media_tag_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("media_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="rule"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tbcc_tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("media_id", "tag_id", name="uq_media_tag_link"),
    )
    op.create_index("ix_media_tag_links_media_id", "media_tag_links", ["media_id"])
    op.create_index("ix_media_tag_links_tag_id", "media_tag_links", ["tag_id"])


def downgrade() -> None:
    op.drop_index("ix_media_tag_links_tag_id", table_name="media_tag_links")
    op.drop_index("ix_media_tag_links_media_id", table_name="media_tag_links")
    op.drop_table("media_tag_links")
    op.drop_index("ix_tbcc_tags_slug", table_name="tbcc_tags")
    op.drop_table("tbcc_tags")
