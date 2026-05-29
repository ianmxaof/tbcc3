"""Per-job Buffer/X caption queue (consumed on Telegram send)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "048_buffer_x_queue"
down_revision = "047_buffer_marketing_pipeline"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("scheduled_text_posts", "buffer_x_queue_json"):
        op.add_column("scheduled_text_posts", sa.Column("buffer_x_queue_json", sa.Text(), nullable=True))


def downgrade() -> None:
    if _has_column("scheduled_text_posts", "buffer_x_queue_json"):
        op.drop_column("scheduled_text_posts", "buffer_x_queue_json")
