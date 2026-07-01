"""Reddit subreddit profiles for rules-aware fan-out."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "083_reddit_subreddit_profiles"
down_revision: Union[str, None] = "082_vip_daily_pull_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reddit_subreddit_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="probation"),
        sa.Column("tier", sa.String(16), nullable=True),
        sa.Column("link_policy", sa.String(24), nullable=False, server_default="bio_style"),
        sa.Column("post_kind", sa.String(16), nullable=False, server_default="image"),
        sa.Column("nsfw_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("required_flair", sa.String(128), nullable=True),
        sa.Column("min_karma", sa.Integer(), nullable=True),
        sa.Column("min_account_age_days", sa.Integer(), nullable=True),
        sa.Column("cooldown_hours", sa.Float(), nullable=False, server_default="72"),
        sa.Column("max_posts_per_day", sa.Float(), nullable=False, server_default="1"),
        sa.Column("max_posts_per_week", sa.Float(), nullable=False, server_default="3"),
        sa.Column("rules_snippet", sa.Text(), nullable=True),
        sa.Column("rules_json", sa.Text(), nullable=True),
        sa.Column("rules_fetched_at", sa.DateTime(), nullable=True),
        sa.Column("skip_reason", sa.String(256), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("last_post_at", sa.DateTime(), nullable=True),
        sa.Column("last_post_ok", sa.Boolean(), nullable=True),
        sa.Column("posts_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("posts_week", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("utc_day", sa.String(10), nullable=True),
        sa.Column("utc_week", sa.String(8), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_reddit_subreddit_profiles_name", "reddit_subreddit_profiles", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_reddit_subreddit_profiles_name", table_name="reddit_subreddit_profiles")
    op.drop_table("reddit_subreddit_profiles")
