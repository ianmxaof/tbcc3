"""loot_creator_submissions — gated review queue for /model creator promos."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "108_loot_creator_submissions"
down_revision: Union[str, None] = "107_click_link_source_ref"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "loot_creator_submissions" in set(insp.get_table_names()):
        return

    op.create_table(
        "loot_creator_submissions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("submitted_url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("platform_key", sa.String(32), nullable=False),
        sa.Column("platform_label", sa.String(32), nullable=False),
        sa.Column("path_handle", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(64), nullable=True),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        sa.Column("modifier_id", sa.Integer(), sa.ForeignKey("loot_modifiers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_loot_creator_submissions_telegram_user_id", "loot_creator_submissions", ["telegram_user_id"])
    op.create_index("ix_loot_creator_submissions_status", "loot_creator_submissions", ["status"])
    op.create_index("ix_loot_creator_submissions_normalized_url", "loot_creator_submissions", ["normalized_url"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "loot_creator_submissions" not in set(insp.get_table_names()):
        return
    op.drop_index("ix_loot_creator_submissions_normalized_url", table_name="loot_creator_submissions")
    op.drop_index("ix_loot_creator_submissions_status", table_name="loot_creator_submissions")
    op.drop_index("ix_loot_creator_submissions_telegram_user_id", table_name="loot_creator_submissions")
    op.drop_table("loot_creator_submissions")
