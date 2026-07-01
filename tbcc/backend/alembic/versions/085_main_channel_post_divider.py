"""main_channel_divider_settings — ornamental spacer images after main-group posts."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "085_main_channel_post_divider"
down_revision: Union[str, None] = "084_reddit_mirror_enabled"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "main_channel_divider_settings" in inspector.get_table_names():
        return
    op.create_table(
        "main_channel_divider_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rotate_images", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("apply_in_topics", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("images_json", sa.Text(), nullable=True),
        sa.Column("active_image_id", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("main_channel_divider_settings")
