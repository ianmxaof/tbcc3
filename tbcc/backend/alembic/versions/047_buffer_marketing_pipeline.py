"""Scheduled posts + listening relay: Buffer / social mirror toggles & relay pacing

Revision ID: 047_buffer_marketing_pipeline
Revises: 046_promo_affiliate_short_url
Create Date: 2026-05-15
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "047_buffer_marketing_pipeline"
down_revision: Union[str, None] = "046_promo_affiliate_short_url"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(table: str) -> set[str]:
    conn = op.get_bind()
    inspector = inspect(conn)
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    st_cols = _cols("scheduled_text_posts")
    if "buffer_mirror_enabled" not in st_cols:
        with op.batch_alter_table("scheduled_text_posts") as b:
            b.add_column(
                sa.Column(
                    "buffer_mirror_enabled",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                )
            )
        op.alter_column("scheduled_text_posts", "buffer_mirror_enabled", server_default=None)

    if "listening_relay_settings" not in inspect(op.get_bind()).get_table_names():
        return
    lr_cols = _cols("listening_relay_settings")

    if "buffer_relay_enabled" not in lr_cols:
        op.add_column(
            "listening_relay_settings",
            sa.Column("buffer_relay_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
        op.alter_column("listening_relay_settings", "buffer_relay_enabled", server_default=None)
    if "buffer_relay_min_interval_minutes" not in lr_cols:
        op.add_column(
            "listening_relay_settings",
            sa.Column("buffer_relay_min_interval_minutes", sa.Integer(), nullable=False, server_default="360"),
        )
        op.alter_column("listening_relay_settings", "buffer_relay_min_interval_minutes", server_default=None)
    if "buffer_relay_max_per_day_utc" not in lr_cols:
        op.add_column(
            "listening_relay_settings",
            sa.Column("buffer_relay_max_per_day_utc", sa.Integer(), nullable=False, server_default="5"),
        )
        op.alter_column("listening_relay_settings", "buffer_relay_max_per_day_utc", server_default=None)
    if "buffer_relay_utc_day" not in lr_cols:
        op.add_column(
            "listening_relay_settings",
            sa.Column("buffer_relay_utc_day", sa.String(length=10), nullable=True),
        )
    if "buffer_relay_posts_today" not in lr_cols:
        op.add_column(
            "listening_relay_settings",
            sa.Column("buffer_relay_posts_today", sa.Integer(), nullable=False, server_default="0"),
        )
        op.alter_column("listening_relay_settings", "buffer_relay_posts_today", server_default=None)
    if "buffer_relay_last_post_at" not in lr_cols:
        op.add_column(
            "listening_relay_settings",
            sa.Column("buffer_relay_last_post_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    st_cols = _cols("scheduled_text_posts")
    if "buffer_mirror_enabled" in st_cols:
        with op.batch_alter_table("scheduled_text_posts") as b:
            b.drop_column("buffer_mirror_enabled")

    if "listening_relay_settings" not in inspect(op.get_bind()).get_table_names():
        return
    lr_cols = _cols("listening_relay_settings")
    for col in (
        "buffer_relay_last_post_at",
        "buffer_relay_posts_today",
        "buffer_relay_utc_day",
        "buffer_relay_max_per_day_utc",
        "buffer_relay_min_interval_minutes",
        "buffer_relay_enabled",
    ):
        if col in lr_cols:
            op.drop_column("listening_relay_settings", col)
