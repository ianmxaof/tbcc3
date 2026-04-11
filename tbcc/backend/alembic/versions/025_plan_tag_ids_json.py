"""Shop products: tag ids from tbcc_tags (JSON list)

Revision ID: 025_plan_tag_ids_json
Revises: 024_description_variations_json
Create Date: 2026-04-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "025_plan_tag_ids_json"
down_revision: Union[str, None] = "024_description_variations_json"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscription_plans",
        sa.Column("plan_tag_ids_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscription_plans", "plan_tag_ids_json")
