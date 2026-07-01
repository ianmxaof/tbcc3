"""reddit_mirror_enabled on scheduled_text_posts."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "084_reddit_mirror_enabled"
down_revision: Union[str, None] = "083_reddit_subreddit_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scheduled_text_posts",
        sa.Column("reddit_mirror_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("scheduled_text_posts", "reddit_mirror_enabled")
