"""Extra description lines for random/cycled Telegram copy

Revision ID: 024_description_variations_json
Revises: 023_bundle_zip_parts_json
Create Date: 2026-04-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "024_description_variations_json"
down_revision: Union[str, None] = "023_bundle_zip_parts_json"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscription_plans",
        sa.Column("description_variations_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscription_plans", "description_variations_json")
