"""media_lane_vision_decisions

Revision ID: 119_media_lane_vision_decisions
Revises: 118_secretary_engagement
Create Date: 2026-08-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "119_media_lane_vision_decisions"
down_revision: Union[str, None] = "118_secretary_engagement"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "media_lane_vision_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("media_id", sa.Integer(), nullable=False),
        sa.Column("lane_key", sa.String(length=32), nullable=True),
        sa.Column("nsfw_tier", sa.String(length=16), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("raw_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_media_lane_vision_decisions_media_id",
        "media_lane_vision_decisions",
        ["media_id"],
    )
    op.create_index(
        "ix_media_lane_vision_decisions_created_at",
        "media_lane_vision_decisions",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_media_lane_vision_decisions_created_at", table_name="media_lane_vision_decisions")
    op.drop_index("ix_media_lane_vision_decisions_media_id", table_name="media_lane_vision_decisions")
    op.drop_table("media_lane_vision_decisions")
