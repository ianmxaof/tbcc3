"""capture_archive_entries: tags column for filter/staging

Revision ID: 067_capture_archive_tags
Revises: 066_campaign_random_channel
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "067_capture_archive_tags"
down_revision: Union[str, None] = "066_campaign_random_channel"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("capture_archive_entries")}
    if "tags" not in cols:
        op.add_column("capture_archive_entries", sa.Column("tags", sa.String(length=500), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("capture_archive_entries")}
    if "tags" in cols:
        op.drop_column("capture_archive_entries", "tags")
