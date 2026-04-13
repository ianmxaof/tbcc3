"""scheduled_text_posts: send_silent, pin_after_send

Revision ID: 029_sched_send_opts
Revises: 028_post_outbound_ev
Create Date: 2026-04-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "029_sched_send_opts"
down_revision: Union[str, None] = "028_post_outbound_ev"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "scheduled_text_posts" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("scheduled_text_posts")}
    if "send_silent" not in cols:
        op.add_column(
            "scheduled_text_posts",
            sa.Column("send_silent", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "pin_after_send" not in cols:
        op.add_column(
            "scheduled_text_posts",
            sa.Column("pin_after_send", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "scheduled_text_posts" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("scheduled_text_posts")}
    if "pin_after_send" in cols:
        op.drop_column("scheduled_text_posts", "pin_after_send")
    if "send_silent" in cols:
        op.drop_column("scheduled_text_posts", "send_silent")
