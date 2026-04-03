"""external_payment_orders: wallet / manual pay before admin marks paid

Revision ID: 016
Revises: 015
"""

from alembic import op
import sqlalchemy as sa

revision = "016_external_payment_orders"
down_revision = "015_referral_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "external_payment_orders" not in insp.get_table_names():
        op.create_table(
            "external_payment_orders",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("telegram_user_id", sa.Integer(), nullable=False),
            sa.Column("plan_id", sa.Integer(), nullable=False),
            sa.Column("reference_code", sa.String(32), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("paid_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["plan_id"], ["subscription_plans.id"], name="fk_external_payment_orders_plan_id"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_external_payment_orders_telegram_user_id", "external_payment_orders", ["telegram_user_id"])
        op.create_index("ix_external_payment_orders_reference_code", "external_payment_orders", ["reference_code"], unique=True)


def downgrade() -> None:
    try:
        op.drop_index("ix_external_payment_orders_reference_code", table_name="external_payment_orders")
    except Exception:
        pass
    try:
        op.drop_index("ix_external_payment_orders_telegram_user_id", table_name="external_payment_orders")
    except Exception:
        pass
    try:
        op.drop_table("external_payment_orders")
    except Exception:
        pass
