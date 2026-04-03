"""Add invite_link to channels, amount_stars to subscriptions

Revision ID: 005
Revises: 004
Create Date: 2026-03-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c["name"] for c in insp.get_columns("channels")]
    if "invite_link" not in cols:
        op.add_column("channels", sa.Column("invite_link", sa.String(), nullable=True))
    sub_cols = [c["name"] for c in insp.get_columns("subscriptions")]
    if "amount_stars" not in sub_cols:
        op.add_column("subscriptions", sa.Column("amount_stars", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("channels", "invite_link")
    op.drop_column("subscriptions", "amount_stars")
