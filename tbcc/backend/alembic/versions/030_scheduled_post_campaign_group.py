"""scheduled_text_posts: campaign_group_id for multi-channel campaigns

Revision ID: 030_sched_campaign
Revises: 029_sched_send_opts
Create Date: 2026-04-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "030_sched_campaign"
down_revision: Union[str, None] = "029_sched_send_opts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "scheduled_text_posts" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("scheduled_text_posts")}
    if "campaign_group_id" not in cols:
        op.add_column(
            "scheduled_text_posts",
            sa.Column("campaign_group_id", sa.String(length=36), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "scheduled_text_posts" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("scheduled_text_posts")}
    if "campaign_group_id" in cols:
        op.drop_column("scheduled_text_posts", "campaign_group_id")
