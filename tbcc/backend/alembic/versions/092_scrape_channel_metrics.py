"""scrape_channel_profiles: lightweight TGStat-style metrics from scrape jobs."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "092_scrape_channel_metrics"
down_revision: Union[str, None] = "091_export_flywheel_ledger"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scrape_channel_profiles", sa.Column("participants_count", sa.Integer(), nullable=True))
    op.add_column("scrape_channel_profiles", sa.Column("avg_views_sample", sa.Float(), nullable=True))
    op.add_column("scrape_channel_profiles", sa.Column("max_views_sample", sa.Integer(), nullable=True))
    op.add_column("scrape_channel_profiles", sa.Column("views_sampled", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("scrape_channel_profiles", sa.Column("invite_link", sa.String(length=512), nullable=True))
    op.add_column("scrape_channel_profiles", sa.Column("suggested_pool_keys", sa.String(length=256), nullable=True))
    op.add_column("scrape_channel_profiles", sa.Column("about", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column("scrape_channel_profiles", "about")
    op.drop_column("scrape_channel_profiles", "suggested_pool_keys")
    op.drop_column("scrape_channel_profiles", "invite_link")
    op.drop_column("scrape_channel_profiles", "views_sampled")
    op.drop_column("scrape_channel_profiles", "max_views_sample")
    op.drop_column("scrape_channel_profiles", "avg_views_sample")
    op.drop_column("scrape_channel_profiles", "participants_count")
