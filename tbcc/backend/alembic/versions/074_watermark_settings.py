"""watermark_settings table

Revision ID: 074_watermark_settings
Revises: 073_import_jobs_job_kind
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa

revision = "074_watermark_settings"
down_revision = "073_import_jobs_job_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watermark_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("enabled", sa.Boolean(), nullable=True),
        sa.Column("text_primary", sa.String(length=120), nullable=True),
        sa.Column("text_secondary", sa.String(length=120), nullable=True),
        sa.Column("text_tertiary", sa.String(length=120), nullable=True),
        sa.Column("opacity", sa.Float(), nullable=True),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.Column("strip_previous", sa.Boolean(), nullable=True),
        sa.Column("apply_on_saved_import", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("apply_on_album_composer", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.execute(
        "INSERT INTO watermark_settings (id, apply_on_saved_import, apply_on_album_composer) "
        "VALUES (1, false, true) ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("watermark_settings")
