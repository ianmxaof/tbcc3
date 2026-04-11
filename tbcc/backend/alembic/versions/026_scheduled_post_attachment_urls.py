"""Scheduled posts: promotional image URLs (same /static/promo/ store as shop)

Revision ID: 026_sched_attach_urls  (must be ≤32 chars — alembic_version.version_num is VARCHAR(32))
Revises: 025_plan_tag_ids_json
Create Date: 2026-04-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "026_sched_attach_urls"
down_revision: Union[str, None] = "025_plan_tag_ids_json"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "scheduled_text_posts" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("scheduled_text_posts")}
    if "attachment_urls_json" not in cols:
        op.add_column(
            "scheduled_text_posts",
            sa.Column("attachment_urls_json", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    try:
        op.drop_column("scheduled_text_posts", "attachment_urls_json")
    except Exception:
        pass
