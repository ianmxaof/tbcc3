"""gatekeeper_lane_labels — gold labels for the online prototype bank

Revision ID: 114_gatekeeper_lane_labels
Revises: 113_secretary_draft_candidates
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "114_gatekeeper_lane_labels"
down_revision: Union[str, None] = "113_secretary_draft_candidates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = set(insp.get_table_names())
    if "gatekeeper_lane_labels" in names:
        return
    op.create_table(
        "gatekeeper_lane_labels",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("media_id", sa.BigInteger(), nullable=True),
        sa.Column("file_unique_id", sa.String(length=128), nullable=False),
        sa.Column("lanes_json", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("embedding_json", sa.Text(), nullable=True),
        sa.Column("dim", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_gatekeeper_lane_labels_file_unique_id",
        "gatekeeper_lane_labels",
        ["file_unique_id"],
    )
    op.create_index(
        "ix_gatekeeper_lane_labels_created_at",
        "gatekeeper_lane_labels",
        ["created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = set(insp.get_table_names())
    if "gatekeeper_lane_labels" not in names:
        return
    op.drop_index("ix_gatekeeper_lane_labels_created_at", table_name="gatekeeper_lane_labels")
    op.drop_index("ix_gatekeeper_lane_labels_file_unique_id", table_name="gatekeeper_lane_labels")
    op.drop_table("gatekeeper_lane_labels")
