"""secretary_user_contexts + secretary_message_records (Format Engine)

Revision ID: 068_secretary_format_engine
Revises: 067_capture_archive_tags
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "068_secretary_format_engine"
down_revision: Union[str, None] = "067_capture_archive_tags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "secretary_user_contexts" not in tables:
        op.create_table(
            "secretary_user_contexts",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
            sa.Column("telegram_username", sa.String(length=128), nullable=True),
            sa.Column("current_phase", sa.String(length=32), nullable=False, server_default="introduction"),
            sa.Column("interaction_format_json", sa.Text(), nullable=True),
            sa.Column("emotional_summary", sa.String(length=512), nullable=True),
            sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_user_at", sa.DateTime(), nullable=True),
            sa.Column("last_assistant_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_secretary_user_contexts_telegram_user_id",
            "secretary_user_contexts",
            ["telegram_user_id"],
            unique=True,
        )

    if "secretary_message_records" not in tables:
        op.create_table(
            "secretary_message_records",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("context_id", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("emotion_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["context_id"], ["secretary_user_contexts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_secretary_message_records_context_id",
            "secretary_message_records",
            ["context_id"],
            unique=False,
        )
        op.create_index(
            "ix_secretary_message_records_created_at",
            "secretary_message_records",
            ["created_at"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())
    if "secretary_message_records" in tables:
        op.drop_index("ix_secretary_message_records_created_at", table_name="secretary_message_records")
        op.drop_index("ix_secretary_message_records_context_id", table_name="secretary_message_records")
        op.drop_table("secretary_message_records")
    if "secretary_user_contexts" in tables:
        op.drop_index("ix_secretary_user_contexts_telegram_user_id", table_name="secretary_user_contexts")
        op.drop_table("secretary_user_contexts")
