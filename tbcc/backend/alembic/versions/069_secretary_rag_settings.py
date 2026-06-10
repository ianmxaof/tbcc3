"""secretary_settings + secretary_knowledge_entries (RAG + admin)

Revision ID: 069_secretary_rag_settings
Revises: 068_secretary_format_engine
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "069_secretary_rag_settings"
down_revision: Union[str, None] = "068_secretary_format_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "secretary_settings" not in tables:
        op.create_table(
            "secretary_settings",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("format_engine_enabled", sa.Boolean(), nullable=True),
            sa.Column("llm_refine_on_phase_change", sa.Boolean(), nullable=True),
            sa.Column("rag_enabled", sa.Boolean(), nullable=True),
            sa.Column("rag_top_k", sa.Integer(), nullable=True),
            sa.Column("system_prompt_extra", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.execute(sa.text("INSERT INTO secretary_settings (id) VALUES (1)"))

    if "secretary_knowledge_entries" not in tables:
        op.create_table(
            "secretary_knowledge_entries",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("title", sa.String(length=256), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("tags", sa.String(length=500), nullable=True),
            sa.Column("source_path", sa.String(length=512), nullable=True),
            sa.Column("chunk_index", sa.Integer(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("embedding_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_secretary_knowledge_source_chunk",
            "secretary_knowledge_entries",
            ["source_path", "chunk_index"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())
    if "secretary_knowledge_entries" in tables:
        op.drop_index("ix_secretary_knowledge_source_chunk", table_name="secretary_knowledge_entries")
        op.drop_table("secretary_knowledge_entries")
    if "secretary_settings" in tables:
        op.drop_table("secretary_settings")
