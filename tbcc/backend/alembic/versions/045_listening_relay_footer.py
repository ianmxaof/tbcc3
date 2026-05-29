"""listening relay: optional footer below scrobble (promo URLs / copy)

Revision ID: 045_listening_relay_footer
Revises: 044_promo_links
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "045_listening_relay_footer"
down_revision: Union[str, None] = "044_promo_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "listening_relay_settings" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("listening_relay_settings")}
    if "message_footer_html" not in cols:
        op.add_column(
            "listening_relay_settings",
            sa.Column("message_footer_html", sa.Text(), nullable=True),
        )
    if "message_footer_variations" not in cols:
        op.add_column(
            "listening_relay_settings",
            sa.Column("message_footer_variations", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "listening_relay_settings" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("listening_relay_settings")}
    if "message_footer_variations" in cols:
        op.drop_column("listening_relay_settings", "message_footer_variations")
    if "message_footer_html" in cols:
        op.drop_column("listening_relay_settings", "message_footer_html")
