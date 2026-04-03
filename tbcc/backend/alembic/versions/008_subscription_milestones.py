"""Add subscription_milestones table for collective rewards

Revision ID: 008
Revises: 007
Create Date: 2026-03-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008"
down_revision: Union[str, None] = "007b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "subscription_milestones" not in insp.get_table_names():
        op.create_table(
            "subscription_milestones",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("threshold", sa.Integer(), nullable=False),
            sa.Column("reward_days", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("triggered_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        # Seed default milestones
        op.execute(
            sa.text(
                "INSERT INTO subscription_milestones (threshold, reward_days) VALUES "
                "(100, 3), (250, 3), (500, 3), (1000, 3)"
            )
        )


def downgrade() -> None:
    op.drop_table("subscription_milestones")
