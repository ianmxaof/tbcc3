"""Add promo_image_url to subscription_plans (shop carousel)

Revision ID: 012
Revises: 011
"""

from alembic import op
import sqlalchemy as sa

revision = "012_promo_image"
down_revision = "011_subscription_charge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "subscription_plans" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("subscription_plans")}
    if "promo_image_url" not in cols:
        op.add_column(
            "subscription_plans",
            sa.Column("promo_image_url", sa.String(length=1024), nullable=True),
        )


def downgrade() -> None:
    try:
        op.drop_column("subscription_plans", "promo_image_url")
    except Exception:
        pass
