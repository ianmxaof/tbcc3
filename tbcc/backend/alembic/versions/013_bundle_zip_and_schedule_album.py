"""bundle zip on plans; per-schedule album_size / pool_randomize

Revision ID: 013
Revises: 012
"""

from alembic import op
import sqlalchemy as sa

revision = "013_bundle_schedule"
down_revision = "012_promo_image"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "subscription_plans" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("subscription_plans")}
        if "bundle_zip_original_name" not in cols:
            op.add_column(
                "subscription_plans",
                sa.Column("bundle_zip_original_name", sa.String(length=512), nullable=True),
            )
    if "scheduled_text_posts" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("scheduled_text_posts")}
        if "album_size" not in cols:
            op.add_column("scheduled_text_posts", sa.Column("album_size", sa.Integer(), nullable=True))
        if "pool_randomize" not in cols:
            op.add_column(
                "scheduled_text_posts",
                sa.Column("pool_randomize", sa.Boolean(), nullable=True),
            )


def downgrade() -> None:
    try:
        op.drop_column("scheduled_text_posts", "pool_randomize")
    except Exception:
        pass
    try:
        op.drop_column("scheduled_text_posts", "album_size")
    except Exception:
        pass
    try:
        op.drop_column("subscription_plans", "bundle_zip_original_name")
    except Exception:
        pass
