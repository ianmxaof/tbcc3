"""subscription_plans: add bot_section for payment-bot menu grouping

Revision ID: 033_plan_bot_section
Revises: 032_route_tiers
Create Date: 2026-04-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "033_plan_bot_section"
down_revision: Union[str, None] = "032_route_tiers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "subscription_plans" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("subscription_plans")}
    if "bot_section" not in cols:
        op.add_column(
            "subscription_plans",
            sa.Column("bot_section", sa.String(length=32), nullable=False, server_default="main"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "subscription_plans" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("subscription_plans")}
    if "bot_section" in cols:
        op.drop_column("subscription_plans", "bot_section")
