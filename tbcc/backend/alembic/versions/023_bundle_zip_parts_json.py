"""JSON list of bundle zip original filenames (N parts)

Revision ID: 023_bundle_zip_parts_json
Revises: 022_bundle_zip2
Create Date: 2026-04-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "023_bundle_zip_parts_json"
down_revision: Union[str, None] = "022_bundle_zip2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscription_plans",
        sa.Column("bundle_zip_parts_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscription_plans", "bundle_zip_parts_json")
