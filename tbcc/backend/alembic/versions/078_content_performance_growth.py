"""Post delivery metrics (Telegram views) + growth attribution events."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "078_content_performance_growth"
down_revision: Union[str, None] = "077_scrape_channel_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = set(insp.get_table_names())

    if "post_delivery_metrics" not in names:
        op.create_table(
            "post_delivery_metrics",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("post_outbound_event_id", sa.Integer(), nullable=True),
            sa.Column("event_type", sa.String(32), nullable=False),
            sa.Column("channel_id", sa.Integer(), nullable=True),
            sa.Column("scheduled_post_id", sa.Integer(), nullable=True),
            sa.Column("pool_id", sa.Integer(), nullable=True),
            sa.Column("scheduler_name", sa.String(256), nullable=True),
            sa.Column("channel_identifier", sa.String(256), nullable=True),
            sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
            sa.Column("telegram_message_ids_json", sa.Text(), nullable=True),
            sa.Column("caption_slot_index", sa.Integer(), nullable=True),
            sa.Column("caption_variation_count", sa.Integer(), nullable=True),
            sa.Column("posted_hour_utc", sa.Integer(), nullable=True),
            sa.Column("posted_hour_local", sa.Integer(), nullable=True),
            sa.Column("timezone_label", sa.String(64), nullable=True),
            sa.Column("views_latest", sa.Integer(), nullable=True),
            sa.Column("views_peak", sa.Integer(), nullable=True),
            sa.Column("forwards_latest", sa.Integer(), nullable=True),
            sa.Column("views_updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index(
            "ix_post_delivery_metrics_scheduled_post_id",
            "post_delivery_metrics",
            ["scheduled_post_id"],
        )
        op.create_index(
            "ix_post_delivery_metrics_channel_id_created",
            "post_delivery_metrics",
            ["channel_id", "created_at"],
        )
        op.create_index(
            "ix_post_delivery_metrics_tg_msg",
            "post_delivery_metrics",
            ["channel_identifier", "telegram_message_id"],
        )

    if "growth_attribution_events" not in names:
        op.create_table(
            "growth_attribution_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("event_type", sa.String(32), nullable=False),
            sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
            sa.Column("amount_stars", sa.Integer(), nullable=True),
            sa.Column("plan_id", sa.Integer(), nullable=True),
            sa.Column("channel_id", sa.Integer(), nullable=True),
            sa.Column("scheduled_post_id", sa.Integer(), nullable=True),
            sa.Column("delivery_metric_id", sa.Integer(), nullable=True),
            sa.Column("caption_slot_index", sa.Integer(), nullable=True),
            sa.Column("posted_hour_local", sa.Integer(), nullable=True),
            sa.Column("context_json", sa.Text(), nullable=True),
        )
        op.create_index(
            "ix_growth_attribution_events_type_created",
            "growth_attribution_events",
            ["event_type", "created_at"],
        )
        op.create_index(
            "ix_growth_attribution_events_user_created",
            "growth_attribution_events",
            ["telegram_user_id", "created_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_growth_attribution_events_user_created", table_name="growth_attribution_events")
    op.drop_index("ix_growth_attribution_events_type_created", table_name="growth_attribution_events")
    op.drop_table("growth_attribution_events")
    op.drop_index("ix_post_delivery_metrics_tg_msg", table_name="post_delivery_metrics")
    op.drop_index("ix_post_delivery_metrics_channel_id_created", table_name="post_delivery_metrics")
    op.drop_index("ix_post_delivery_metrics_scheduled_post_id", table_name="post_delivery_metrics")
    op.drop_table("post_delivery_metrics")
