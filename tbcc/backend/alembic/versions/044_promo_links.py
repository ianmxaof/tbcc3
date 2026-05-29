"""promo_affiliate_links for dashboard promo picker

Revision ID: 044_promo_links
Revises: 043_relay_template_rotation
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "044_promo_links"
down_revision: Union[str, None] = "043_relay_template_rotation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "promo_affiliate_links" in inspector.get_table_names():
        return
    op.create_table(
        "promo_affiliate_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("label", sa.String(length=512), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("payout_kind", sa.String(length=16), nullable=False, server_default="other"),
        sa.Column("payout_detail", sa.String(length=64), nullable=True),
        sa.Column("priority_tier", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("promo_affiliate_links")
