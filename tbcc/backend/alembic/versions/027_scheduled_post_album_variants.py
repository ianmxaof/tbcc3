"""Scheduled posts: album variants + order mode (shuffle / carousel)

Revision ID: 027_sched_album_variants  (must be ≤32 chars — alembic_version.version_num is VARCHAR(32))
Revises: 026_sched_attach_urls
Create Date: 2026-04-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "027_sched_album_variants"
down_revision: Union[str, None] = "026_sched_attach_urls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "scheduled_text_posts" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("scheduled_text_posts")}
    if "album_variants_json" not in cols:
        op.add_column("scheduled_text_posts", sa.Column("album_variants_json", sa.Text(), nullable=True))
    if "album_order_mode" not in cols:
        op.add_column("scheduled_text_posts", sa.Column("album_order_mode", sa.String(16), nullable=True))
    if "album_carousel_index" not in cols:
        op.add_column("scheduled_text_posts", sa.Column("album_carousel_index", sa.Integer(), nullable=True))


def downgrade() -> None:
    for col in ("album_carousel_index", "album_order_mode", "album_variants_json"):
        try:
            op.drop_column("scheduled_text_posts", col)
        except Exception:
            pass
