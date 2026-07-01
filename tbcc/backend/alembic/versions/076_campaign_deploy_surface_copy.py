"""Campaign deploy ledger + optional per-surface copy on scheduled posts."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "076_campaign_deploy_surface_copy"
down_revision: Union[str, None] = "075_relay_buffer_x_queue"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "campaign_deploy_events" not in insp.get_table_names():
        op.create_table(
            "campaign_deploy_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("scheduled_post_id", sa.Integer(), nullable=True),
            sa.Column("campaign_group_id", sa.String(36), nullable=True),
            sa.Column("trigger", sa.String(32), nullable=False, server_default="api"),
            sa.Column("telegram_status", sa.String(16), nullable=False, server_default="skipped"),
            sa.Column("telegram_error", sa.Text(), nullable=True),
            sa.Column("buffer_status", sa.String(16), nullable=False, server_default="skipped"),
            sa.Column("buffer_error", sa.Text(), nullable=True),
            sa.Column("discord_status", sa.String(16), nullable=False, server_default="skipped"),
            sa.Column("discord_error", sa.Text(), nullable=True),
            sa.Column("surfaces_json", sa.Text(), nullable=True),
        )

    if not _has_column("scheduled_text_posts", "surface_copy_json"):
        op.add_column("scheduled_text_posts", sa.Column("surface_copy_json", sa.Text(), nullable=True))
    if not _has_column("scheduled_text_posts", "discord_mirror_enabled"):
        op.add_column(
            "scheduled_text_posts",
            sa.Column("discord_mirror_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    if _has_column("scheduled_text_posts", "discord_mirror_enabled"):
        op.drop_column("scheduled_text_posts", "discord_mirror_enabled")
    if _has_column("scheduled_text_posts", "surface_copy_json"):
        op.drop_column("scheduled_text_posts", "surface_copy_json")
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "campaign_deploy_events" in insp.get_table_names():
        op.drop_table("campaign_deploy_events")
