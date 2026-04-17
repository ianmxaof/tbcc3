"""scheduled_text_posts: auto-pause after repeated send failures

Revision ID: 034_sched_auto_pause
Revises: 033_plan_bot_section
Create Date: 2026-04-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "034_sched_auto_pause"
down_revision: Union[str, None] = "033_plan_bot_section"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "scheduled_text_posts" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("scheduled_text_posts")}
    if "send_failure_streak" not in cols:
        op.add_column("scheduled_text_posts", sa.Column("send_failure_streak", sa.Integer(), nullable=True))
    if "posting_auto_paused_at" not in cols:
        op.add_column("scheduled_text_posts", sa.Column("posting_auto_paused_at", sa.DateTime(), nullable=True))
    if "posting_auto_pause_reason" not in cols:
        op.add_column(
            "scheduled_text_posts",
            sa.Column("posting_auto_pause_reason", sa.String(length=512), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "scheduled_text_posts" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("scheduled_text_posts")}
    if "posting_auto_pause_reason" in cols:
        op.drop_column("scheduled_text_posts", "posting_auto_pause_reason")
    if "posting_auto_paused_at" in cols:
        op.drop_column("scheduled_text_posts", "posting_auto_paused_at")
    if "send_failure_streak" in cols:
        op.drop_column("scheduled_text_posts", "send_failure_streak")
