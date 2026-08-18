"""secretary_engagement_tracking

Revision ID: 118_secretary_engagement
Revises: 117_conversion_playbooks
Create Date: 2026-08-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "118_secretary_engagement"
down_revision: Union[str, None] = "117_conversion_playbooks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "secretary_user_contexts",
        sa.Column("engagement_score", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "secretary_user_contexts",
        sa.Column("funnel_stage", sa.String(length=16), nullable=False, server_default="cold"),
    )


def downgrade() -> None:
    op.drop_column("secretary_user_contexts", "funnel_stage")
    op.drop_column("secretary_user_contexts", "engagement_score")
