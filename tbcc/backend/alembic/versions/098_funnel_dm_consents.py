"""funnel_dm_consents — human-gate DM opt-in for paced outreach."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "098_funnel_dm_consents"
down_revision: Union[str, None] = "097_funnel_strategy_entries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "funnel_dm_consents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.Integer(), nullable=False),
        sa.Column("gate_target", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=128), nullable=True),
        sa.Column("invite_url", sa.String(length=512), nullable=True),
        sa.Column("dm_opt_in", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("acknowledged_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id"),
    )
    op.create_index("ix_funnel_dm_consents_telegram_user_id", "funnel_dm_consents", ["telegram_user_id"])


def downgrade() -> None:
    op.drop_index("ix_funnel_dm_consents_telegram_user_id", table_name="funnel_dm_consents")
    op.drop_table("funnel_dm_consents")
