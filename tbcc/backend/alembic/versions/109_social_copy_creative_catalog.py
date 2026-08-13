"""social_copy_templates + creative_catalog_entries."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "109_social_copy_creative_catalog"
down_revision: Union[str, None] = "108_loot_creator_submissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = set(insp.get_table_names())

    if "social_copy_templates" not in names:
        op.create_table(
            "social_copy_templates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("category", sa.String(64), nullable=False),
            sa.Column("surface", sa.String(32), nullable=False, server_default="x_buffer"),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("image_hint", sa.String(32), nullable=True),
            sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_uses_before_demote", sa.Integer(), nullable=False, server_default="2"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_social_copy_templates_category", "social_copy_templates", ["category"])
        op.create_index("ix_social_copy_templates_surface", "social_copy_templates", ["surface"])

    if "creative_catalog_entries" not in names:
        op.create_table(
            "creative_catalog_entries",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("entry_type", sa.String(32), nullable=False),
            sa.Column("campaign", sa.String(128), nullable=True),
            sa.Column("catalog_key", sa.String(128), nullable=True),
            sa.Column("surface", sa.String(32), nullable=True),
            sa.Column("lane_key", sa.String(32), nullable=True),
            sa.Column("title", sa.String(256), nullable=True),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("master_json", sa.Text(), nullable=True),
            sa.Column("subject_delta", sa.Text(), nullable=True),
            sa.Column("tags_json", sa.Text(), nullable=True),
            sa.Column("prompt_gate_key", sa.String(128), nullable=True),
            sa.Column("asset_url", sa.String(1024), nullable=True),
            sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_creative_catalog_entry_type", "creative_catalog_entries", ["entry_type"])
        op.create_index("ix_creative_catalog_campaign", "creative_catalog_entries", ["campaign"])
        op.create_index("ix_creative_catalog_catalog_key", "creative_catalog_entries", ["catalog_key"])
        op.create_index("ix_creative_catalog_prompt_gate_key", "creative_catalog_entries", ["prompt_gate_key"])


def downgrade() -> None:
    op.drop_table("creative_catalog_entries")
    op.drop_table("social_copy_templates")
