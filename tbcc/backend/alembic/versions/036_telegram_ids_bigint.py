"""convert telegram id columns to bigint

Revision ID: 036_telegram_ids_bigint
Revises: 035_plan_nowpayments_metadata
Create Date: 2026-04-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "036_telegram_ids_bigint"
down_revision: Union[str, None] = "035_plan_nowpayments_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(insp: sa.Inspector, table: str, col: str) -> bool:
    try:
        cols = {c["name"] for c in insp.get_columns(table)}
    except Exception:
        return False
    return col in cols


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    dialect = conn.dialect.name

    # PostgreSQL: explicit cast is safest for existing integer columns.
    if dialect == "postgresql":
        if _has_column(insp, "external_payment_orders", "telegram_user_id"):
            op.execute(
                "ALTER TABLE external_payment_orders "
                "ALTER COLUMN telegram_user_id TYPE BIGINT USING telegram_user_id::bigint"
            )
        if _has_column(insp, "subscriptions", "telegram_user_id"):
            op.execute(
                "ALTER TABLE subscriptions "
                "ALTER COLUMN telegram_user_id TYPE BIGINT USING telegram_user_id::bigint"
            )
        if _has_column(insp, "subscriptions", "referrer_id"):
            op.execute(
                "ALTER TABLE subscriptions "
                "ALTER COLUMN referrer_id TYPE BIGINT USING referrer_id::bigint"
            )
        if _has_column(insp, "referral_codes", "telegram_user_id"):
            op.execute(
                "ALTER TABLE referral_codes "
                "ALTER COLUMN telegram_user_id TYPE BIGINT USING telegram_user_id::bigint"
            )
        if _has_column(insp, "referral_tracking", "referred_user_id"):
            op.execute(
                "ALTER TABLE referral_tracking "
                "ALTER COLUMN referred_user_id TYPE BIGINT USING referred_user_id::bigint"
            )
        if _has_column(insp, "referral_tracking", "referrer_user_id"):
            op.execute(
                "ALTER TABLE referral_tracking "
                "ALTER COLUMN referrer_user_id TYPE BIGINT USING referrer_user_id::bigint"
            )
        return

    # Non-PostgreSQL fallback.
    if _has_column(insp, "external_payment_orders", "telegram_user_id"):
        op.alter_column("external_payment_orders", "telegram_user_id", type_=sa.BigInteger(), existing_type=sa.Integer())
    if _has_column(insp, "subscriptions", "telegram_user_id"):
        op.alter_column("subscriptions", "telegram_user_id", type_=sa.BigInteger(), existing_type=sa.Integer())
    if _has_column(insp, "subscriptions", "referrer_id"):
        op.alter_column("subscriptions", "referrer_id", type_=sa.BigInteger(), existing_type=sa.Integer())
    if _has_column(insp, "referral_codes", "telegram_user_id"):
        op.alter_column("referral_codes", "telegram_user_id", type_=sa.BigInteger(), existing_type=sa.Integer())
    if _has_column(insp, "referral_tracking", "referred_user_id"):
        op.alter_column("referral_tracking", "referred_user_id", type_=sa.BigInteger(), existing_type=sa.Integer())
    if _has_column(insp, "referral_tracking", "referrer_user_id"):
        op.alter_column("referral_tracking", "referrer_user_id", type_=sa.BigInteger(), existing_type=sa.Integer())


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    dialect = conn.dialect.name

    if dialect == "postgresql":
        if _has_column(insp, "external_payment_orders", "telegram_user_id"):
            op.execute(
                "ALTER TABLE external_payment_orders "
                "ALTER COLUMN telegram_user_id TYPE INTEGER USING telegram_user_id::integer"
            )
        if _has_column(insp, "subscriptions", "telegram_user_id"):
            op.execute(
                "ALTER TABLE subscriptions "
                "ALTER COLUMN telegram_user_id TYPE INTEGER USING telegram_user_id::integer"
            )
        if _has_column(insp, "subscriptions", "referrer_id"):
            op.execute(
                "ALTER TABLE subscriptions "
                "ALTER COLUMN referrer_id TYPE INTEGER USING referrer_id::integer"
            )
        if _has_column(insp, "referral_codes", "telegram_user_id"):
            op.execute(
                "ALTER TABLE referral_codes "
                "ALTER COLUMN telegram_user_id TYPE INTEGER USING telegram_user_id::integer"
            )
        if _has_column(insp, "referral_tracking", "referred_user_id"):
            op.execute(
                "ALTER TABLE referral_tracking "
                "ALTER COLUMN referred_user_id TYPE INTEGER USING referred_user_id::integer"
            )
        if _has_column(insp, "referral_tracking", "referrer_user_id"):
            op.execute(
                "ALTER TABLE referral_tracking "
                "ALTER COLUMN referrer_user_id TYPE INTEGER USING referrer_user_id::integer"
            )
        return

    if _has_column(insp, "external_payment_orders", "telegram_user_id"):
        op.alter_column("external_payment_orders", "telegram_user_id", type_=sa.Integer(), existing_type=sa.BigInteger())
    if _has_column(insp, "subscriptions", "telegram_user_id"):
        op.alter_column("subscriptions", "telegram_user_id", type_=sa.Integer(), existing_type=sa.BigInteger())
    if _has_column(insp, "subscriptions", "referrer_id"):
        op.alter_column("subscriptions", "referrer_id", type_=sa.Integer(), existing_type=sa.BigInteger())
    if _has_column(insp, "referral_codes", "telegram_user_id"):
        op.alter_column("referral_codes", "telegram_user_id", type_=sa.Integer(), existing_type=sa.BigInteger())
    if _has_column(insp, "referral_tracking", "referred_user_id"):
        op.alter_column("referral_tracking", "referred_user_id", type_=sa.Integer(), existing_type=sa.BigInteger())
    if _has_column(insp, "referral_tracking", "referrer_user_id"):
        op.alter_column("referral_tracking", "referrer_user_id", type_=sa.Integer(), existing_type=sa.BigInteger())
