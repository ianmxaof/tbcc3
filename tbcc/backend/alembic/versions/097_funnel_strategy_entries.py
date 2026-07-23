"""funnel_strategy_entries — placement / conversion playbook RAG."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "097_funnel_strategy_entries"
down_revision: Union[str, None] = "096_scheduled_delete_after_pin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "funnel_strategy_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=256), nullable=True),
        sa.Column("pattern", sa.String(length=64), nullable=False),
        sa.Column("surface", sa.String(length=32), nullable=False),
        sa.Column("copy_template", sa.Text(), nullable=True),
        sa.Column("visual_notes", sa.Text(), nullable=True),
        sa.Column("screenshot_ref", sa.String(length=512), nullable=True),
        sa.Column("risk_tags", sa.String(length=256), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("embedding_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_funnel_strategy_surface", "funnel_strategy_entries", ["surface"])
    op.create_index("ix_funnel_strategy_pattern", "funnel_strategy_entries", ["pattern"])


def downgrade() -> None:
    op.drop_index("ix_funnel_strategy_pattern", table_name="funnel_strategy_entries")
    op.drop_index("ix_funnel_strategy_surface", table_name="funnel_strategy_entries")
    op.drop_table("funnel_strategy_entries")
