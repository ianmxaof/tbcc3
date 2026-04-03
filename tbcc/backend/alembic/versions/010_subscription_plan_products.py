"""Add description, is_active, product_type to subscription_plans (shop products)

Revision ID: 010
Revises: 009
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010_subscription_plan_products"
down_revision: Union[str, None] = "009_pool_randomize"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "subscription_plans" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("subscription_plans")}
    if "description" not in cols:
        op.add_column("subscription_plans", sa.Column("description", sa.Text(), nullable=True))
    if "is_active" not in cols:
        op.add_column(
            "subscription_plans",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    if "product_type" not in cols:
        op.add_column(
            "subscription_plans",
            sa.Column("product_type", sa.String(length=32), nullable=False, server_default="subscription"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "subscription_plans" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("subscription_plans")}
    if "product_type" in cols:
        op.drop_column("subscription_plans", "product_type")
    if "is_active" in cols:
        op.drop_column("subscription_plans", "is_active")
    if "description" in cols:
        op.drop_column("subscription_plans", "description")
