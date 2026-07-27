"""prompt_gates — Linkvertise Text asset registry for gated prompt SKUs."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "103_prompt_gates"
down_revision: Union[str, None] = "102_goblin_claim_bigint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prompt_gates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("prompt_ref", sa.String(length=256), nullable=True),
        sa.Column("prompt_body", sa.Text(), nullable=True),
        sa.Column("body_hash", sa.String(length=64), nullable=True),
        sa.Column("lv_url", sa.String(length=1024), nullable=True),
        sa.Column("lv_asset_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("tier", sa.String(length=64), nullable=True),
        sa.Column(
            "surface_policy",
            sa.String(length=32),
            nullable=False,
            server_default="telegram_only",
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_probe_at", sa.DateTime(), nullable=True),
        sa.Column("last_probe_flags", sa.Text(), nullable=True),
        sa.Column("superseded_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["prompt_gates.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prompt_gates_key", "prompt_gates", ["key"])
    op.create_index("ix_prompt_gates_status", "prompt_gates", ["status"])
    op.create_index("ix_prompt_gates_key_status", "prompt_gates", ["key", "status"])


def downgrade() -> None:
    op.drop_index("ix_prompt_gates_key_status", table_name="prompt_gates")
    op.drop_index("ix_prompt_gates_status", table_name="prompt_gates")
    op.drop_index("ix_prompt_gates_key", table_name="prompt_gates")
    op.drop_table("prompt_gates")
