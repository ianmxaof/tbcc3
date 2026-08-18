"""add_userbot_outreach_tables

Revision ID: 116_add_userbot_outreach_tables
Revises: 115_secretary_psych_markers
Create Date: 2026-08-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "116_add_userbot_outreach_tables"
down_revision: Union[str, None] = "115_secretary_psych_markers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # WarmupState enum — the column below creates the named type once via the
    # table's enum (Alembic op.create_table emits CREATE TYPE regardless of
    # create_type=False, so an explicit CREATE TYPE here would double-create).
    op.create_table(
        "userbot_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("phone_number", sa.String(), nullable=False),
        sa.Column("session_file_path", sa.String(), nullable=False),
        sa.Column("proxy_json", sa.Text(), nullable=True),
        sa.Column(
            "warmup_state",
            sa.Enum("cold", "warming", "warm", name="warmupstate"),
            nullable=False,
            server_default="cold",
        ),
        sa.Column("daily_message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_daily_limit", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("is_banned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "last_activity_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("reset_daily_counts", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone_number"),
    )

    # TargetStatus enum — same pattern: single create via the column enum.
    op.create_table(
        "cold_targets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_username", sa.String(), nullable=True),
        sa.Column("telegram_user_id", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column(
            "assigned_userbot_id",
            sa.Integer(),
            sa.ForeignKey("userbot_accounts.id"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Enum("new", "contacted", "engaging", "converted", "dead", name="targetstatus"),
            nullable=False,
            server_default="new",
        ),
        sa.Column("first_contact_at", sa.DateTime(), nullable=True),
        sa.Column("last_contact_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("notes", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("cold_targets")
    op.execute("DROP TYPE targetstatus")

    op.drop_table("userbot_accounts")
    op.execute("DROP TYPE warmupstate")
