"""Loot overseer: Buffer → X mirror when daily AOF promo posts."""

from alembic import op
import sqlalchemy as sa

revision = "060_loot_buffer_mirror"
down_revision = "059_loot_free_pulls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "loot_bot_settings",
        sa.Column("buffer_mirror_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "loot_bot_settings",
        sa.Column("buffer_publish_now", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("loot_bot_settings", sa.Column("buffer_x_queue_json", sa.Text(), nullable=True))
    op.alter_column("loot_bot_settings", "buffer_mirror_enabled", server_default=None)
    op.alter_column("loot_bot_settings", "buffer_publish_now", server_default=None)


def downgrade() -> None:
    op.drop_column("loot_bot_settings", "buffer_x_queue_json")
    op.drop_column("loot_bot_settings", "buffer_publish_now")
    op.drop_column("loot_bot_settings", "buffer_mirror_enabled")
