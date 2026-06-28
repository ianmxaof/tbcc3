"""income_entries ledger for unified revenue rollup

Revision ID: 088_income_ledger
Revises: 087_industry_benchmarks
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "088_income_ledger"
down_revision: Union[str, None] = "087_industry_benchmarks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "income_entries" not in inspector.get_table_names():
        op.create_table(
            "income_entries",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("idempotency_key", sa.String(length=128), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("source_label", sa.String(length=256), nullable=True),
            sa.Column("amount_minor", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(length=8), nullable=False),
            sa.Column("amount_usd_cents", sa.Integer(), nullable=False),
            sa.Column("earned_at", sa.DateTime(), nullable=True),
            sa.Column("sync_kind", sa.String(length=16), nullable=False, server_default="computed"),
            sa.Column("external_ref", sa.String(length=128), nullable=True),
            sa.Column("subscription_id", sa.Integer(), nullable=True),
            sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
            sa.Column("raw_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_income_entries_idempotency_key", "income_entries", ["idempotency_key"], unique=True)
        op.create_index("ix_income_entries_source", "income_entries", ["source"])
        op.create_index("ix_income_entries_earned_at", "income_entries", ["earned_at"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "income_entries" in inspector.get_table_names():
        op.drop_index("ix_income_entries_earned_at", table_name="income_entries")
        op.drop_index("ix_income_entries_source", table_name="income_entries")
        op.drop_index("ix_income_entries_idempotency_key", table_name="income_entries")
        op.drop_table("income_entries")
