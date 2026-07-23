"""scheduled_text_posts: delete_after_pin_seconds for ephemeral pin liveness."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "096_scheduled_delete_after_pin"
down_revision: Union[str, None] = "095_click_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("scheduled_text_posts")}
    if "delete_after_pin_seconds" not in cols:
        op.add_column(
            "scheduled_text_posts",
            sa.Column("delete_after_pin_seconds", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("scheduled_text_posts")}
    if "delete_after_pin_seconds" in cols:
        op.drop_column("scheduled_text_posts", "delete_after_pin_seconds")
