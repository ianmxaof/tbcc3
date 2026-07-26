"""buyer_entitlements — channel-independent paid access ledger."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "093_buyer_entitlements"
down_revision: Union[str, None] = "092_scrape_channel_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "buyer_entitlements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("network_key", sa.String(length=64), nullable=True),
        sa.Column("plan_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("primary_channel_ident", sa.String(length=64), nullable=True),
        sa.Column("backup_channel_ident", sa.String(length=64), nullable=True),
        sa.Column("last_invite_url", sa.String(length=512), nullable=True),
        sa.Column("last_reissued_at", sa.DateTime(), nullable=True),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_buyer_entitlements_telegram_user_id", "buyer_entitlements", ["telegram_user_id"])
    op.create_index("ix_buyer_entitlements_kind", "buyer_entitlements", ["kind"])
    op.create_index("ix_buyer_entitlements_network_key", "buyer_entitlements", ["network_key"])
    op.create_index("ix_buyer_entitlements_status", "buyer_entitlements", ["status"])


def downgrade() -> None:
    op.drop_index("ix_buyer_entitlements_status", table_name="buyer_entitlements")
    op.drop_index("ix_buyer_entitlements_network_key", table_name="buyer_entitlements")
    op.drop_index("ix_buyer_entitlements_kind", table_name="buyer_entitlements")
    op.drop_index("ix_buyer_entitlements_telegram_user_id", table_name="buyer_entitlements")
    op.drop_table("buyer_entitlements")
