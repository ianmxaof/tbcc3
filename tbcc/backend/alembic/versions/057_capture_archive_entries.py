"""capture archive entries (master URL/username list)

Revision ID: 057_capture_archive
Revises: 056_aof_x_promo_defaults
Create Date: 2026-05-23

"""

from alembic import op
import sqlalchemy as sa

revision = "057_capture_archive"
down_revision = "056_aof_x_promo_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capture_archive_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=True),
        sa.Column("ref", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("origin", sa.String(length=32), nullable=True),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "value", name="uq_capture_archive_kind_value"),
    )
    op.create_index("ix_capture_archive_kind_added", "capture_archive_entries", ["kind", "added_at"])


def downgrade() -> None:
    op.drop_index("ix_capture_archive_kind_added", table_name="capture_archive_entries")
    op.drop_table("capture_archive_entries")
