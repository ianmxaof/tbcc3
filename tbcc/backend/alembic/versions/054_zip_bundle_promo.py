"""zip bundle global promo insert (readme + image inside zips)

Revision ID: 054_zip_bundle_promo
Revises: 053_listening_relay_copy_block
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "054_zip_bundle_promo"
down_revision: Union[str, None] = "053_listening_relay_copy_block"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "zip_bundle_settings" in inspector.get_table_names():
        return
    op.create_table(
        "zip_bundle_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("include_text_file", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("text_filename", sa.String(length=128), nullable=False, server_default="TBCC_README.txt"),
        sa.Column("text_body", sa.Text(), nullable=True),
        sa.Column("include_image", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("image_filename", sa.String(length=128), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("zip_bundle_settings")
