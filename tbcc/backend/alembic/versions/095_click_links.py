"""click_links + click_link_hits — promo click beacon."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "095_click_links"
down_revision: Union[str, None] = "094_lane_drops"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "click_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("destination_url", sa.String(length=2048), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("active", sa.Integer(), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_click_links_slug", "click_links", ["slug"])
    op.create_table(
        "click_link_hits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("link_id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.String(length=128), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("referer", sa.String(length=512), nullable=True),
        sa.Column("country", sa.String(length=8), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["link_id"], ["click_links.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_click_link_hits_link_id", "click_link_hits", ["link_id"])


def downgrade() -> None:
    op.drop_index("ix_click_link_hits_link_id", table_name="click_link_hits")
    op.drop_table("click_link_hits")
    op.drop_index("ix_click_links_slug", table_name="click_links")
    op.drop_table("click_links")
