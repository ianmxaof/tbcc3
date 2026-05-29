"""import_jobs table for fast async import pipeline

Revision ID: 062_import_jobs
Revises: 061_loot_referrals_bonus
"""

from alembic import op
import sqlalchemy as sa

revision = "062_import_jobs"
down_revision = "061_loot_referrals_bonus"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(length=32), nullable=False, server_default="stored"),
        sa.Column("pool_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("saved_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(length=512), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("filename", sa.String(length=256), nullable=True),
        sa.Column("media_type", sa.String(length=32), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("staging_path", sa.String(length=1024), nullable=True),
        sa.Column("poster_path", sa.String(length=1024), nullable=True),
        sa.Column("media_id", sa.Integer(), nullable=True),
        sa.Column("extension_job_id", sa.String(length=64), nullable=True),
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_jobs_status_updated", "import_jobs", ["status", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_import_jobs_status_updated", table_name="import_jobs")
    op.drop_table("import_jobs")
