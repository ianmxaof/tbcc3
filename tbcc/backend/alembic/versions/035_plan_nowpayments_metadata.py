"""subscription_plans: per-product NOWPayments metadata fields

Revision ID: 035_plan_nowpayments_metadata
Revises: 034_sched_auto_pause
Create Date: 2026-04-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "035_plan_nowpayments_metadata"
down_revision: Union[str, None] = "034_sched_auto_pause"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "subscription_plans" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("subscription_plans")}
    if "nowpayments_price_usd" not in cols:
        op.add_column("subscription_plans", sa.Column("nowpayments_price_usd", sa.Float(), nullable=True))
    if "nowpayments_allow_any_currency" not in cols:
        op.add_column(
            "subscription_plans",
            sa.Column("nowpayments_allow_any_currency", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    if "nowpayments_pay_currency" not in cols:
        op.add_column("subscription_plans", sa.Column("nowpayments_pay_currency", sa.String(length=64), nullable=True))
    if "nowpayments_receiving_wallet" not in cols:
        op.add_column(
            "subscription_plans",
            sa.Column("nowpayments_receiving_wallet", sa.String(length=255), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "subscription_plans" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("subscription_plans")}
    if "nowpayments_receiving_wallet" in cols:
        op.drop_column("subscription_plans", "nowpayments_receiving_wallet")
    if "nowpayments_pay_currency" in cols:
        op.drop_column("subscription_plans", "nowpayments_pay_currency")
    if "nowpayments_allow_any_currency" in cols:
        op.drop_column("subscription_plans", "nowpayments_allow_any_currency")
    if "nowpayments_price_usd" in cols:
        op.drop_column("subscription_plans", "nowpayments_price_usd")
