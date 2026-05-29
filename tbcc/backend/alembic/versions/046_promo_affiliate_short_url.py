"""promo_affiliate_links: optional short_url for inserts / promos

Revision ID: 046_promo_affiliate_short_url
Revises: 045_listening_relay_footer
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "046_promo_affiliate_short_url"
down_revision: Union[str, None] = "045_listening_relay_footer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "promo_affiliate_links" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("promo_affiliate_links")}
    if "short_url" not in cols:
        op.add_column("promo_affiliate_links", sa.Column("short_url", sa.Text(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "promo_affiliate_links" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("promo_affiliate_links")}
    if "short_url" in cols:
        op.drop_column("promo_affiliate_links", "short_url")
