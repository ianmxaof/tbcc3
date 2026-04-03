"""scheduled_text_posts: forum topic (message_thread_id)

Revision ID: 017
Revises: 016
Create Date: 2025-03-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# Must be ≤32 chars — alembic_version.version_num is VARCHAR(32)
revision: str = "017_scheduled_forum_topic"
down_revision: Union[str, None] = "016_external_payment_orders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scheduled_text_posts",
        sa.Column("message_thread_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scheduled_text_posts", "message_thread_id")
