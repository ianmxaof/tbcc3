"""source_ref on click_links — join beacon clicks to funnel touches and revenue."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "107_click_link_source_ref"
down_revision: Union[str, None] = "106_loot_daily_pull"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = set(insp.get_table_names())
    if "click_links" not in names:
        return

    cols = {c["name"] for c in insp.get_columns("click_links")}
    if "source_ref" not in cols:
        op.add_column("click_links", sa.Column("source_ref", sa.String(64), nullable=True))
        op.create_index("ix_click_links_source_ref", "click_links", ["source_ref"])

        # Backfill from any ?start= payload already baked into the destination.
        op.execute(
            """
            UPDATE click_links
               SET source_ref = substring(destination_url from '[?&]start=(src_[A-Za-z0-9_]+)')
             WHERE destination_url LIKE '%%start=src_%%'
            """
            if bind.dialect.name == "postgresql"
            else """
            UPDATE click_links
               SET source_ref = NULL
             WHERE 1 = 0
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = set(insp.get_table_names())
    if "click_links" not in names:
        return

    cols = {c["name"] for c in insp.get_columns("click_links")}
    if "source_ref" in cols:
        indexes = {i["name"] for i in insp.get_indexes("click_links")}
        if "ix_click_links_source_ref" in indexes:
            op.drop_index("ix_click_links_source_ref", table_name="click_links")
        op.drop_column("click_links", "source_ref")
