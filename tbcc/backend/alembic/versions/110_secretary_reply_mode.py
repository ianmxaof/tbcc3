"""secretary_user_contexts.reply_mode for per-customer Pilot/Auto

Revision ID: 110_secretary_reply_mode
Revises: 109_social_copy_creative_catalog
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "110_secretary_reply_mode"
down_revision: Union[str, None] = "109_social_copy_creative_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("secretary_user_contexts")}
    if "reply_mode" not in cols:
        op.add_column(
            "secretary_user_contexts",
            sa.Column("reply_mode", sa.String(length=16), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("secretary_user_contexts")}
    if "reply_mode" in cols:
        op.drop_column("secretary_user_contexts", "reply_mode")
