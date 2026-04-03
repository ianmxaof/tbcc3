"""Add referral tracking and referrer_id to subscriptions

Revision ID: 007
Revises: 006
Create Date: 2026-03-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()
    if "referral_tracking" not in tables:
        op.create_table(
            "referral_tracking",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("referred_user_id", sa.Integer(), nullable=False),
            sa.Column("referrer_user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    sub_cols = [c["name"] for c in insp.get_columns("subscriptions")]
    if "referrer_id" not in sub_cols:
        op.add_column("subscriptions", sa.Column("referrer_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("subscriptions", "referrer_id")
    op.drop_table("referral_tracking")
