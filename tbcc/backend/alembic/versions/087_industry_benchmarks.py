"""industry_benchmarks table for IIU-style external priors

Revision ID: 087_industry_benchmarks
Revises: 086_promo_affiliate_placements
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "087_industry_benchmarks"
down_revision: Union[str, None] = "086_promo_affiliate_placements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "industry_benchmarks" not in inspector.get_table_names():
        op.create_table(
            "industry_benchmarks",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("slug", sa.String(length=128), nullable=False),
            sa.Column("title", sa.String(length=256), nullable=False),
            sa.Column("topic_type", sa.String(length=32), nullable=False, server_default="category"),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("demand_index", sa.Float(), nullable=True),
            sa.Column("benchmark_json", sa.Text(), nullable=True),
            sa.Column("source_url", sa.String(length=512), nullable=True),
            sa.Column("source_label", sa.String(length=64), nullable=True),
            sa.Column("effective_year", sa.Integer(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug"),
        )
        op.create_index("ix_industry_benchmarks_slug", "industry_benchmarks", ["slug"], unique=True)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "industry_benchmarks" in inspector.get_table_names():
        op.drop_index("ix_industry_benchmarks_slug", table_name="industry_benchmarks")
        op.drop_table("industry_benchmarks")
