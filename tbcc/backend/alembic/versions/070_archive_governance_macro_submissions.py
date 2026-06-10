"""archive governance + macro search source submissions

Revision ID: 070_archive_governance
Revises: 069_secretary_rag_settings
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "070_archive_governance"
down_revision: Union[str, None] = "069_secretary_rag_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("capture_archive_entries")}
    if "status" not in cols:
        op.add_column(
            "capture_archive_entries",
            sa.Column("status", sa.String(length=16), nullable=False, server_default="approved"),
        )
    if "submitted_by" not in cols:
        op.add_column("capture_archive_entries", sa.Column("submitted_by", sa.String(length=32), nullable=True))

    tables = set(insp.get_table_names())
    if "macro_search_source_submissions" not in tables:
        op.create_table(
            "macro_search_source_submissions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("url_template", sa.Text(), nullable=False),
            sa.Column("sample_username", sa.String(length=64), nullable=True),
            sa.Column("sample_search_url", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
            sa.Column("submitted_by", sa.String(length=32), nullable=True),
            sa.Column("reviewed_by", sa.String(length=32), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_macro_source_submissions_status_created",
            "macro_search_source_submissions",
            ["status", "created_at"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())
    if "macro_search_source_submissions" in tables:
        op.drop_index("ix_macro_source_submissions_status_created", table_name="macro_search_source_submissions")
        op.drop_table("macro_search_source_submissions")
    cols = {c["name"] for c in insp.get_columns("capture_archive_entries")}
    if "submitted_by" in cols:
        op.drop_column("capture_archive_entries", "submitted_by")
    if "status" in cols:
        op.drop_column("capture_archive_entries", "status")
