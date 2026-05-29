"""Per-job Buffer shareNow (publish immediately) vs addToQueue."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "049_buffer_publish_now"
down_revision = "048_buffer_x_queue"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("scheduled_text_posts", "buffer_publish_now"):
        op.add_column(
            "scheduled_text_posts",
            sa.Column("buffer_publish_now", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.alter_column("scheduled_text_posts", "buffer_publish_now", server_default=None)


def downgrade() -> None:
    if _has_column("scheduled_text_posts", "buffer_publish_now"):
        op.drop_column("scheduled_text_posts", "buffer_publish_now")
