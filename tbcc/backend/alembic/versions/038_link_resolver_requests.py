"""link_resolver_requests: ad-link bypass queue + results

Revision ID: 038_link_resolver
Revises: 037_sched_checkout_stars
Create Date: 2026-05-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "038_link_resolver"
down_revision: Union[str, None] = "037_sched_checkout_stars"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "link_resolver_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("tier", sa.String(length=16), nullable=False, server_default="free"),
        sa.Column("input_url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("final_url", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(length=16), nullable=True),
        sa.Column("provider_latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_detail", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_link_resolver_requests_public_id",
        "link_resolver_requests",
        ["public_id"],
        unique=True,
    )
    op.create_index(
        "ix_link_resolver_requests_telegram_user_id",
        "link_resolver_requests",
        ["telegram_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_link_resolver_requests_telegram_user_id", table_name="link_resolver_requests")
    op.drop_index("ix_link_resolver_requests_public_id", table_name="link_resolver_requests")
    op.drop_table("link_resolver_requests")
