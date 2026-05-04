"""scheduled_text_posts: optional Telegram Stars checkout button (payment bot deep link)

Revision ID: 037_sched_checkout_stars
Revises: 036_telegram_ids_bigint
Create Date: 2026-04-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "037_sched_checkout_stars"
down_revision: Union[str, None] = "036_telegram_ids_bigint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "scheduled_text_posts" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("scheduled_text_posts")}
    if "checkout_stars_enabled" not in cols:
        op.add_column(
            "scheduled_text_posts",
            sa.Column("checkout_stars_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "checkout_stars_plan_id" not in cols:
        op.add_column("scheduled_text_posts", sa.Column("checkout_stars_plan_id", sa.Integer(), nullable=True))
    if "checkout_button_label" not in cols:
        op.add_column(
            "scheduled_text_posts",
            sa.Column("checkout_button_label", sa.String(length=64), nullable=True),
        )
    if "checkout_referral_code" not in cols:
        op.add_column(
            "scheduled_text_posts",
            sa.Column("checkout_referral_code", sa.String(length=16), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "scheduled_text_posts" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("scheduled_text_posts")}
    if "checkout_referral_code" in cols:
        op.drop_column("scheduled_text_posts", "checkout_referral_code")
    if "checkout_button_label" in cols:
        op.drop_column("scheduled_text_posts", "checkout_button_label")
    if "checkout_stars_plan_id" in cols:
        op.drop_column("scheduled_text_posts", "checkout_stars_plan_id")
    if "checkout_stars_enabled" in cols:
        op.drop_column("scheduled_text_posts", "checkout_stars_enabled")
