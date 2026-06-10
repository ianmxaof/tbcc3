"""import_jobs.job_kind for channel/topic background imports

Revision ID: 073_import_jobs_job_kind
Revises: 072_capture_archive_description
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "073_import_jobs_job_kind"
down_revision: Union[str, None] = "072_capture_archive_description"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "import_jobs",
        sa.Column("job_kind", sa.String(length=32), nullable=False, server_default="bytes"),
    )


def downgrade() -> None:
    op.drop_column("import_jobs", "job_kind")
