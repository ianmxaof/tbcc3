"""user_funnel_touches + traffic source columns on subscriptions and growth attribution."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "104_traffic_attribution"
down_revision: Union[str, None] = "103_prompt_gates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = set(insp.get_table_names())

    if "user_funnel_touches" not in names:
        op.create_table(
            "user_funnel_touches",
            sa.Column("telegram_user_id", sa.BigInteger(), primary_key=True),
            sa.Column("first_source_ref", sa.String(64), nullable=True),
            sa.Column("first_entry_payload", sa.String(128), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(), nullable=True),
            sa.Column("last_source_ref", sa.String(64), nullable=True),
            sa.Column("last_entry_payload", sa.String(128), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(), nullable=True),
            sa.Column("touch_count", sa.Integer(), nullable=False, server_default="0"),
        )

    cols_sub = {c["name"] for c in insp.get_columns("subscriptions")} if "subscriptions" in names else set()
    if "traffic_source_ref" not in cols_sub:
        op.add_column("subscriptions", sa.Column("traffic_source_ref", sa.String(64), nullable=True))
    if "traffic_entry_payload" not in cols_sub:
        op.add_column("subscriptions", sa.Column("traffic_entry_payload", sa.String(128), nullable=True))

    cols_ga = (
        {c["name"] for c in insp.get_columns("growth_attribution_events")}
        if "growth_attribution_events" in names
        else set()
    )
    if "traffic_source_ref" not in cols_ga:
        op.add_column("growth_attribution_events", sa.Column("traffic_source_ref", sa.String(64), nullable=True))
    if "start_payload_raw" not in cols_ga:
        op.add_column("growth_attribution_events", sa.Column("start_payload_raw", sa.String(128), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = set(insp.get_table_names())

    if "growth_attribution_events" in names:
        cols = {c["name"] for c in insp.get_columns("growth_attribution_events")}
        if "start_payload_raw" in cols:
            op.drop_column("growth_attribution_events", "start_payload_raw")
        if "traffic_source_ref" in cols:
            op.drop_column("growth_attribution_events", "traffic_source_ref")

    if "subscriptions" in names:
        cols = {c["name"] for c in insp.get_columns("subscriptions")}
        if "traffic_entry_payload" in cols:
            op.drop_column("subscriptions", "traffic_entry_payload")
        if "traffic_source_ref" in cols:
            op.drop_column("subscriptions", "traffic_source_ref")

    if "user_funnel_touches" in names:
        op.drop_table("user_funnel_touches")
