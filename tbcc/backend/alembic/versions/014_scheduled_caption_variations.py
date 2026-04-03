"""scheduled posts: rotating caption variations

Revision ID: 014
Revises: 013
"""

from alembic import op
import sqlalchemy as sa

revision = "014_caption_variations"
down_revision = "013_bundle_schedule"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "scheduled_text_posts" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("scheduled_text_posts")}
        if "content_variations" not in cols:
            op.add_column(
                "scheduled_text_posts",
                sa.Column("content_variations", sa.Text(), nullable=True),
            )
        if "caption_rotation_index" not in cols:
            op.add_column(
                "scheduled_text_posts",
                sa.Column("caption_rotation_index", sa.Integer(), nullable=True),
            )


def downgrade() -> None:
    try:
        op.drop_column("scheduled_text_posts", "caption_rotation_index")
    except Exception:
        pass
    try:
        op.drop_column("scheduled_text_posts", "content_variations")
    except Exception:
        pass
