"""Add interval, media, and buttons to scheduled_text_posts

Revision ID: 007b
Revises: 007a
Create Date: 2026-03-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007b"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scheduled_text_posts", sa.Column("interval_minutes", sa.Integer(), nullable=True))
    op.add_column("scheduled_text_posts", sa.Column("last_posted_at", sa.DateTime(), nullable=True))
    op.add_column("scheduled_text_posts", sa.Column("media_ids", sa.Text(), nullable=True))
    op.add_column("scheduled_text_posts", sa.Column("pool_id", sa.Integer(), nullable=True))
    op.add_column("scheduled_text_posts", sa.Column("buttons", sa.Text(), nullable=True))
    op.alter_column("scheduled_text_posts", "scheduled_at", nullable=True)


def downgrade() -> None:
    op.alter_column("scheduled_text_posts", "scheduled_at", nullable=False)
    op.drop_column("scheduled_text_posts", "buttons")
    op.drop_column("scheduled_text_posts", "pool_id")
    op.drop_column("scheduled_text_posts", "media_ids")
    op.drop_column("scheduled_text_posts", "last_posted_at")
    op.drop_column("scheduled_text_posts", "interval_minutes")
