"""promo_affiliate_links: placements, network_keys, copy_template + rotation cursors

Revision ID: 086_promo_affiliate_placements
Revises: 085_main_channel_post_divider
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "086_promo_affiliate_placements"
down_revision: Union[str, None] = "085_main_channel_post_divider"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "promo_affiliate_links" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("promo_affiliate_links")}
        if "placements_json" not in cols:
            op.add_column("promo_affiliate_links", sa.Column("placements_json", sa.Text(), nullable=True))
        if "network_keys_json" not in cols:
            op.add_column("promo_affiliate_links", sa.Column("network_keys_json", sa.Text(), nullable=True))
        if "copy_template" not in cols:
            op.add_column("promo_affiliate_links", sa.Column("copy_template", sa.Text(), nullable=True))

    if "promo_affiliate_rotation_cursors" not in inspector.get_table_names():
        op.create_table(
            "promo_affiliate_rotation_cursors",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("placement", sa.String(length=32), nullable=False),
            sa.Column("network_key", sa.String(length=32), nullable=False, server_default=""),
            sa.Column("cursor_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("placement", "network_key", name="uq_promo_affiliate_rotation_cursor"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "promo_affiliate_rotation_cursors" in inspector.get_table_names():
        op.drop_table("promo_affiliate_rotation_cursors")
    if "promo_affiliate_links" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("promo_affiliate_links")}
        if "copy_template" in cols:
            op.drop_column("promo_affiliate_links", "copy_template")
        if "network_keys_json" in cols:
            op.drop_column("promo_affiliate_links", "network_keys_json")
        if "placements_json" in cols:
            op.drop_column("promo_affiliate_links", "placements_json")
