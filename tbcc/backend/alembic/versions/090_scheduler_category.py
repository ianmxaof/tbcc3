"""scheduler_category on scheduled_text_posts."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "090_scheduler_category"
down_revision: Union[str, None] = "089_erome_mirror_enabled"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scheduled_text_posts",
        sa.Column("scheduler_category", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scheduled_text_posts", "scheduler_category")
