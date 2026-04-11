"""post_outbound_events — append-only log for dashboard analytics

Revision ID: 028_post_outbound_ev
Revises: 027_sched_album_variants
Create Date: 2026-04-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "028_post_outbound_ev"
down_revision: Union[str, None] = "027_sched_album_variants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "post_outbound_events" in insp.get_table_names():
        return
    op.create_table(
        "post_outbound_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("scheduled_post_id", sa.Integer(), nullable=True),
        sa.Column("pool_id", sa.Integer(), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("extra_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("post_outbound_events")
