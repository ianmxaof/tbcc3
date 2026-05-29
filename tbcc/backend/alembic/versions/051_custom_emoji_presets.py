"""Custom emoji preset library for Telethon HTML captions

Revision ID: 051_custom_emoji_presets
Revises: 050_caption_llm_rewrite
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "051_custom_emoji_presets"
down_revision: Union[str, None] = "050_caption_llm_rewrite"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "custom_emoji_presets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("html_fragment", sa.Text(), nullable=False),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("custom_emoji_presets")
