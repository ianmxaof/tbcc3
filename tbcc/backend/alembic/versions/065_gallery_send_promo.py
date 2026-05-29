"""Gallery send-promo tail images for batch sends

Revision ID: 065_gallery_send_promo
Revises: 064_scrape_runs
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "065_gallery_send_promo"
down_revision = "064_scrape_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "gallery_send_promo_settings" in inspector.get_table_names():
        return
    op.create_table(
        "gallery_send_promo_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("images_json", sa.Text(), nullable=True),
        sa.Column("active_image_id", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("gallery_send_promo_settings")
