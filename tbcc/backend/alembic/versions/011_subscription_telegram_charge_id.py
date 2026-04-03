"""telegram_payment_charge_id on subscriptions (idempotent Stars payments)

Revision ID: 011
Revises: 010
"""

from alembic import op
import sqlalchemy as sa

revision = "011_subscription_charge"
down_revision = "010_subscription_plan_products"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("subscriptions")} if "subscriptions" in insp.get_table_names() else set()
    if "telegram_payment_charge_id" not in cols:
        op.add_column(
            "subscriptions",
            sa.Column("telegram_payment_charge_id", sa.String(length=128), nullable=True),
        )
    # Unique index (Postgres/SQLite)
    try:
        op.create_index(
            "ix_subscriptions_telegram_payment_charge_id",
            "subscriptions",
            ["telegram_payment_charge_id"],
            unique=True,
        )
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_index("ix_subscriptions_telegram_payment_charge_id", table_name="subscriptions")
    except Exception:
        pass
    try:
        op.drop_column("subscriptions", "telegram_payment_charge_id")
    except Exception:
        pass
