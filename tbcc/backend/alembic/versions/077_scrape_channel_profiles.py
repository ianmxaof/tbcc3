"""Inbound channel intel backlog — forward policy, AOF lane, posting cadence."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "077_scrape_channel_profiles"
down_revision: Union[str, None] = "076_campaign_deploy_surface_copy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "scrape_channel_profiles" in insp.get_table_names():
        return
    op.create_table(
        "scrape_channel_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("username", sa.String(128), nullable=True),
        sa.Column("identifier", sa.String(256), nullable=True),
        sa.Column("forward_enabled", sa.Boolean(), nullable=True),
        sa.Column("forward_probe_at", sa.DateTime(), nullable=True),
        sa.Column("skip_reason", sa.String(256), nullable=True),
        sa.Column("pool_key", sa.String(32), nullable=True),
        sa.Column("pool_name", sa.String(128), nullable=True),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("folder_label", sa.String(128), nullable=True),
        sa.Column("tags_sample", sa.Text(), nullable=True),
        sa.Column("posts_per_day", sa.Float(), nullable=True),
        sa.Column("posts_per_week", sa.Float(), nullable=True),
        sa.Column("posts_per_month", sa.Float(), nullable=True),
        sa.Column("messages_sampled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_post_at", sa.DateTime(), nullable=True),
        sa.Column("cadence_span_days", sa.Float(), nullable=True),
        sa.Column("cadence_json", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_scrape_channel_profiles_chat_id", "scrape_channel_profiles", ["chat_id"], unique=True)
    op.create_index("ix_scrape_channel_profiles_source_id", "scrape_channel_profiles", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_scrape_channel_profiles_source_id", table_name="scrape_channel_profiles")
    op.drop_index("ix_scrape_channel_profiles_chat_id", table_name="scrape_channel_profiles")
    op.drop_table("scrape_channel_profiles")
