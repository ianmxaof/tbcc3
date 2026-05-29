"""emoji_factory_sketch_pages — persistent design scratchbook

Revision ID: 063_emoji_factory_sketchbook
Revises: 062_import_jobs
"""

from alembic import op
import sqlalchemy as sa

revision = "063_emoji_factory_sketchbook"
down_revision = "062_import_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "emoji_factory_sketch_pages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("title", sa.String(length=256), nullable=True),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_emoji_factory_sketch_pages_sort_order",
        "emoji_factory_sketch_pages",
        ["sort_order"],
    )


def downgrade() -> None:
    op.drop_index("ix_emoji_factory_sketch_pages_sort_order", table_name="emoji_factory_sketch_pages")
    op.drop_table("emoji_factory_sketch_pages")
