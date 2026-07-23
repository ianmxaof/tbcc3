"""lane_drops — merch checkpoint before dedicated lane channel."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "094_lane_drops"
down_revision: Union[str, None] = "093_buyer_entitlements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lane_drops",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("network_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=True),
        sa.Column("promo_path", sa.Text(), nullable=True),
        sa.Column("lane_path", sa.Text(), nullable=True),
        sa.Column("vault_path", sa.Text(), nullable=True),
        sa.Column("glimpse_manifest_json", sa.Text(), nullable=True),
        sa.Column("destination_url", sa.String(length=1024), nullable=True),
        sa.Column("primary_gate_url", sa.String(length=1024), nullable=True),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lane_drops_network_key", "lane_drops", ["network_key"])
    op.create_index("ix_lane_drops_status", "lane_drops", ["status"])


def downgrade() -> None:
    op.drop_index("ix_lane_drops_status", table_name="lane_drops")
    op.drop_index("ix_lane_drops_network_key", table_name="lane_drops")
    op.drop_table("lane_drops")
