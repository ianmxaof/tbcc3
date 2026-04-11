"""Second optional bundle zip (split pack)

Revision ID: 022_bundle_zip2
Revises: 021_promo_image_urls_json
Create Date: 2026-04-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "022_bundle_zip2"
down_revision: Union[str, None] = "021_promo_image_urls_json"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscription_plans",
        sa.Column("bundle_zip2_original_name", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscription_plans", "bundle_zip2_original_name")
