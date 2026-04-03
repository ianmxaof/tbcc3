"""referral_codes: unique short codes per Telegram user for ref_* deep links

Revision ID: 015
Revises: 014
"""

from alembic import op
import sqlalchemy as sa

revision = "015_referral_codes"
down_revision = "014_caption_variations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "referral_codes" not in insp.get_table_names():
        op.create_table(
            "referral_codes",
            sa.Column("telegram_user_id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(16), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("telegram_user_id", name="pk_referral_codes_telegram_user_id"),
        )
        op.create_index("ix_referral_codes_code", "referral_codes", ["code"], unique=True)


def downgrade() -> None:
    try:
        op.drop_index("ix_referral_codes_code", table_name="referral_codes")
    except Exception:
        pass
    try:
        op.drop_table("referral_codes")
    except Exception:
        pass
