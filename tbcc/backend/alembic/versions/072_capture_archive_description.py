"""capture_archive_entries: description column for auto-tag summaries

Revision ID: 072_capture_archive_description
Revises: 071_pool_collective_random
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "072_capture_archive_description"
down_revision: Union[str, None] = "071_pool_collective_random"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("capture_archive_entries")}
    if "description" not in cols:
        op.add_column("capture_archive_entries", sa.Column("description", sa.String(length=400), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("capture_archive_entries")}
    if "description" in cols:
        op.drop_column("capture_archive_entries", "description")
