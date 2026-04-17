"""media: nsfw_tier + classification_json; content_pools: route_match_tag_slugs + route_priority

Revision ID: 031_class_route
Revises: 030_sched_campaign
Create Date: 2026-04-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "031_class_route"
down_revision: Union[str, None] = "030_sched_campaign"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if "media" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("media")}
        if "nsfw_tier" not in cols:
            op.add_column("media", sa.Column("nsfw_tier", sa.String(length=16), nullable=True))
        if "classification_json" not in cols:
            op.add_column("media", sa.Column("classification_json", sa.Text(), nullable=True))

    if "content_pools" in insp.get_table_names():
        cp_cols = {c["name"] for c in insp.get_columns("content_pools")}
        if "route_match_tag_slugs" not in cp_cols:
            op.add_column(
                "content_pools",
                sa.Column("route_match_tag_slugs", sa.String(length=512), nullable=True),
            )
        if "route_priority" not in cp_cols:
            op.add_column(
                "content_pools",
                sa.Column("route_priority", sa.Integer(), nullable=False, server_default="100"),
            )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if "content_pools" in insp.get_table_names():
        cp_cols = {c["name"] for c in insp.get_columns("content_pools")}
        if "route_priority" in cp_cols:
            op.drop_column("content_pools", "route_priority")
        if "route_match_tag_slugs" in cp_cols:
            op.drop_column("content_pools", "route_match_tag_slugs")

    if "media" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("media")}
        if "classification_json" in cols:
            op.drop_column("media", "classification_json")
        if "nsfw_tier" in cols:
            op.drop_column("media", "nsfw_tier")
