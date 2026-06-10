"""scheduled_text_posts: campaign_random_channel (one random channel per interval)

Revision ID: 066_campaign_random_channel
Revises: 065_gallery_send_promo
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "066_campaign_random_channel"
down_revision: Union[str, None] = "065_gallery_send_promo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "scheduled_text_posts" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("scheduled_text_posts")}
    if "campaign_random_channel" not in cols:
        op.add_column(
            "scheduled_text_posts",
            sa.Column(
                "campaign_random_channel",
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
    if "campaign_random_channel" in cols:
        op.drop_column("scheduled_text_posts", "campaign_random_channel")
