"""traffic_source_ref on income_entries — tie ledger dollars back to a traffic source."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "105_income_traffic_source"
down_revision: Union[str, None] = "104_traffic_attribution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = set(insp.get_table_names())
    if "income_entries" not in names:
        return

    cols = {c["name"] for c in insp.get_columns("income_entries")}
    if "traffic_source_ref" not in cols:
        op.add_column("income_entries", sa.Column("traffic_source_ref", sa.String(64), nullable=True))
        op.create_index(
            "ix_income_entries_traffic_source_ref",
            "income_entries",
            ["traffic_source_ref"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = set(insp.get_table_names())
    if "income_entries" not in names:
        return

    cols = {c["name"] for c in insp.get_columns("income_entries")}
    if "traffic_source_ref" in cols:
        indexes = {i["name"] for i in insp.get_indexes("income_entries")}
        if "ix_income_entries_traffic_source_ref" in indexes:
            op.drop_index("ix_income_entries_traffic_source_ref", table_name="income_entries")
        op.drop_column("income_entries", "traffic_source_ref")
