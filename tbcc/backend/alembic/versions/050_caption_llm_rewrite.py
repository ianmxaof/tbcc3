"""Per scheduled job: optional LLM caption rewrite (random or every N sends)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "050_caption_llm_rewrite"
down_revision = "049_buffer_publish_now"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    cols = [
        ("caption_llm_rewrite_enabled", sa.Boolean(), False),
        ("caption_llm_rewrite_mode", sa.String(16), None),
        ("caption_llm_rewrite_interval", sa.Integer(), None),
        ("caption_llm_rewrite_probability", sa.Float(), None),
        ("caption_llm_send_count", sa.Integer(), 0),
        ("last_sent_caption_html", sa.Text(), None),
    ]
    for name, col_type, default in cols:
        if _has_column("scheduled_text_posts", name):
            continue
        if default is False:
            op.add_column(
                "scheduled_text_posts",
                sa.Column(name, col_type, nullable=False, server_default=sa.false()),
            )
            op.alter_column("scheduled_text_posts", name, server_default=None)
        elif default == 0:
            op.add_column(
                "scheduled_text_posts",
                sa.Column(name, col_type, nullable=False, server_default="0"),
            )
            op.alter_column("scheduled_text_posts", name, server_default=None)
        else:
            op.add_column("scheduled_text_posts", sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    for name in (
        "last_sent_caption_html",
        "caption_llm_send_count",
        "caption_llm_rewrite_probability",
        "caption_llm_rewrite_interval",
        "caption_llm_rewrite_mode",
        "caption_llm_rewrite_enabled",
    ):
        if _has_column("scheduled_text_posts", name):
            op.drop_column("scheduled_text_posts", name)
