"""content_pools: route_nsfw_tiers for tier-based auto-routing

Revision ID: 032_route_tiers
Revises: 031_class_route
Create Date: 2026-04-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "032_route_tiers"
down_revision: Union[str, None] = "031_class_route"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "content_pools" not in insp.get_table_names():
        return
    cp_cols = {c["name"] for c in insp.get_columns("content_pools")}
    if "route_nsfw_tiers" not in cp_cols:
        op.add_column(
            "content_pools",
            sa.Column("route_nsfw_tiers", sa.String(length=128), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "content_pools" not in insp.get_table_names():
        return
    cp_cols = {c["name"] for c in insp.get_columns("content_pools")}
    if "route_nsfw_tiers" in cp_cols:
        op.drop_column("content_pools", "route_nsfw_tiers")
