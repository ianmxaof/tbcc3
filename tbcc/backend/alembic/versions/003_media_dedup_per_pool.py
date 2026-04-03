"""Allow same media in different pools (dedup per pool)

Revision ID: 003
Revises: 002
Create Date: 2026-03-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        # SQLite cannot alter constraints; recreate table with new unique (file_unique_id, pool_id)
        op.create_table(
            "media_new",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("telegram_message_id", sa.Integer(), nullable=False),
            sa.Column("file_id", sa.String(), nullable=False),
            sa.Column("file_unique_id", sa.String(), nullable=False),
            sa.Column("media_type", sa.String(), nullable=True),
            sa.Column("source_channel", sa.String(), nullable=True),
            sa.Column("tags", sa.String(), nullable=True),
            sa.Column("pool_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(), server_default="pending", nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("file_unique_id", "pool_id", name="uq_media_file_unique_id_pool_id"),
        )
        op.execute(
            "INSERT INTO media_new (id, telegram_message_id, file_id, file_unique_id, media_type, "
            "source_channel, tags, pool_id, status, created_at) "
            "SELECT id, telegram_message_id, file_id, file_unique_id, media_type, "
            "source_channel, tags, pool_id, status, created_at FROM media"
        )
        op.drop_table("media")
        op.execute("ALTER TABLE media_new RENAME TO media")
    elif conn.dialect.name == "postgresql":
        # 001 used UniqueConstraint("file_unique_id") without a name. PostgreSQL often
        # names it media_file_unique_id_key, not uq_media_file_unique_id — drop by lookup.
        while True:
            row = conn.execute(
                sa.text(
                    """
                    SELECT c.conname
                    FROM pg_constraint c
                    JOIN pg_class t ON c.conrelid = t.oid
                    JOIN pg_namespace n ON n.oid = t.relnamespace
                    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
                    WHERE n.nspname = current_schema()
                      AND t.relname = 'media'
                      AND c.contype = 'u'
                      AND array_length(c.conkey, 1) = 1
                      AND a.attname = 'file_unique_id'
                    """
                )
            ).fetchone()
            if not row:
                break
            # Identifier from pg_catalog; quote for safety
            op.execute(sa.text('ALTER TABLE media DROP CONSTRAINT "' + row[0].replace('"', '""') + '"'))
        op.create_unique_constraint(
            "uq_media_file_unique_id_pool_id",
            "media",
            ["file_unique_id", "pool_id"],
        )
    else:
        with op.batch_alter_table("media") as batch_op:
            batch_op.drop_constraint("uq_media_file_unique_id", type_="unique")
            batch_op.create_unique_constraint(
                "uq_media_file_unique_id_pool_id",
                ["file_unique_id", "pool_id"],
            )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        op.create_table(
            "media_old",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("telegram_message_id", sa.Integer(), nullable=False),
            sa.Column("file_id", sa.String(), nullable=False),
            sa.Column("file_unique_id", sa.String(), nullable=False),
            sa.Column("media_type", sa.String(), nullable=True),
            sa.Column("source_channel", sa.String(), nullable=True),
            sa.Column("tags", sa.String(), nullable=True),
            sa.Column("pool_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(), server_default="pending", nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("file_unique_id"),
        )
        op.execute(
            "INSERT INTO media_old SELECT id, telegram_message_id, file_id, file_unique_id, "
            "media_type, source_channel, tags, pool_id, status, created_at FROM media"
        )
        op.drop_table("media")
        op.execute("ALTER TABLE media_old RENAME TO media")
    else:
        with op.batch_alter_table("media") as batch_op:
            batch_op.drop_constraint("uq_media_file_unique_id_pool_id", type_="unique")
            batch_op.create_unique_constraint("uq_media_file_unique_id", ["file_unique_id"])
