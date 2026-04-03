"""Add subscription_plans and link subscriptions

Revision ID: 004
Revises: 003
Create Date: 2026-03-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # Create subscription_plans if not exists (idempotent for partial migration)
    insp = sa.inspect(conn)
    if "subscription_plans" not in insp.get_table_names():
        op.create_table(
            "subscription_plans",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("price_stars", sa.Integer(), server_default="0", nullable=True),
            sa.Column("duration_days", sa.Integer(), server_default="30", nullable=True),
            sa.Column("channel_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["channel_id"], ["channels.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    # Add plan_id to subscriptions (skip if already present)
    cols = [c["name"] for c in insp.get_columns("subscriptions")]
    if "plan_id" not in cols:
        op.add_column("subscriptions", sa.Column("plan_id", sa.Integer(), nullable=True))
        if conn.dialect.name != "sqlite":
            op.create_foreign_key("fk_subscriptions_plan_id", "subscriptions", "subscription_plans", ["plan_id"], ["id"])


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "sqlite":
        op.drop_constraint("fk_subscriptions_plan_id", "subscriptions", type_="foreignkey")
    op.drop_column("subscriptions", "plan_id")
    op.drop_table("subscription_plans")
