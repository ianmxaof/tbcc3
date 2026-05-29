"""listening relay: rotating HTML templates (Last.fm + webhook)

Revision ID: 043_relay_template_rotation
Revises: 042_listening_relay_settings
Create Date: 2026-05-10

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "043_relay_template_rotation"
down_revision: Union[str, None] = "042_listening_relay_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Safe when TBCC API startup already ALTER'd these columns (duplicate alembic vs main.py)."""
    conn = op.get_bind()
    inspector = inspect(conn)
    if "listening_relay_settings" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("listening_relay_settings")}
    if "message_template_variations" not in cols:
        op.add_column(
            "listening_relay_settings",
            sa.Column("message_template_variations", sa.Text(), nullable=True),
        )
    if "message_template_rotation_index" not in cols:
        op.add_column(
            "listening_relay_settings",
            sa.Column("message_template_rotation_index", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "listening_relay_settings" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("listening_relay_settings")}
    if "message_template_rotation_index" in cols:
        op.drop_column("listening_relay_settings", "message_template_rotation_index")
    if "message_template_variations" in cols:
        op.drop_column("listening_relay_settings", "message_template_variations")
