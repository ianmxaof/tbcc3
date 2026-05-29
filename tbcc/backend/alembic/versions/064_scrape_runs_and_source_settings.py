"""scrape_runs table + per-source scrape settings

Revision ID: 064_scrape_runs
Revises: 063_emoji_factory_sketchbook
"""

from alembic import op
import sqlalchemy as sa

revision = "064_scrape_runs"
down_revision = "063_emoji_factory_sketchbook"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("schedule_cron", sa.String(length=64), nullable=True))
    op.add_column(
        "sources",
        sa.Column("schedule_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "sources",
        sa.Column("media_types", sa.String(length=16), nullable=False, server_default="both"),
    )
    op.add_column(
        "sources",
        sa.Column("max_messages_per_run", sa.Integer(), nullable=False, server_default="50"),
    )
    op.add_column("sources", sa.Column("last_scraped_at", sa.DateTime(), nullable=True))

    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=256), nullable=True),
        sa.Column("pool_id", sa.Integer(), nullable=True),
        sa.Column("trigger", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("messages_scanned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stored", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_duplicate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_media_type", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_no_media", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("errors_json", sa.Text(), nullable=True),
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scrape_runs_source_created", "scrape_runs", ["source_id", "created_at"])
    op.create_index("ix_scrape_runs_status_created", "scrape_runs", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_scrape_runs_status_created", table_name="scrape_runs")
    op.drop_index("ix_scrape_runs_source_created", table_name="scrape_runs")
    op.drop_table("scrape_runs")
    op.drop_column("sources", "last_scraped_at")
    op.drop_column("sources", "max_messages_per_run")
    op.drop_column("sources", "media_types")
    op.drop_column("sources", "schedule_enabled")
    op.drop_column("sources", "schedule_cron")
