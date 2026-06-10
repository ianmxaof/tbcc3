"""scheduled_text_posts: pool_collective_random (pick a random pool each send)

Revision ID: 071_pool_collective_random
Revises: 070_archive_governance
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "071_pool_collective_random"
down_revision: Union[str, None] = "070_archive_governance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "scheduled_text_posts" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("scheduled_text_posts")}
    if "pool_collective_random" not in cols:
        op.add_column(
            "scheduled_text_posts",
            sa.Column(
                "pool_collective_random",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "scheduled_text_posts" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("scheduled_text_posts")}
    if "pool_collective_random" in cols:
        op.drop_column("scheduled_text_posts", "pool_collective_random")
