"""channel webhook_url for outbound Discord/custom notifications

Revision ID: 019_channel_webhook_url
Revises: 018_growth_settings
Create Date: 2026-04-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "019_channel_webhook_url"
down_revision: Union[str, None] = "018_growth_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("channels", sa.Column("webhook_url", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column("channels", "webhook_url")
