"""Subscription plan promo image album (JSON array, max 5 URLs)

Revision ID: 021_promo_image_urls_json
Revises: 020_tbcc_structured_tags
Create Date: 2026-04-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "021_promo_image_urls_json"
down_revision: Union[str, None] = "020_tbcc_structured_tags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscription_plans",
        sa.Column("promo_image_urls_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscription_plans", "promo_image_urls_json")
