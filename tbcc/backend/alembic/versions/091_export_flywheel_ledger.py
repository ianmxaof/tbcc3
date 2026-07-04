"""post_delivery_metrics: export flywheel ledger columns."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "091_export_flywheel_ledger"
down_revision: Union[str, None] = "090_scheduler_category"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("post_delivery_metrics", sa.Column("media_ids_json", sa.Text(), nullable=True))
    op.add_column("post_delivery_metrics", sa.Column("network_key", sa.String(length=32), nullable=True))
    op.add_column("post_delivery_metrics", sa.Column("export_source", sa.String(length=32), nullable=True))
    op.add_column("post_delivery_metrics", sa.Column("surface", sa.String(length=32), nullable=True))
    op.add_column("post_delivery_metrics", sa.Column("external_post_id", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("post_delivery_metrics", "external_post_id")
    op.drop_column("post_delivery_metrics", "surface")
    op.drop_column("post_delivery_metrics", "export_source")
    op.drop_column("post_delivery_metrics", "network_key")
    op.drop_column("post_delivery_metrics", "media_ids_json")
