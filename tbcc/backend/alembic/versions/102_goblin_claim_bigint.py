"""Fix goblin_claim.telegram_user_id for 64-bit Telegram IDs.

Revision ID: 102_goblin_claim_bigint
Revises: 101_goblin_drops
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "102_goblin_claim_bigint"
down_revision: Union[str, None] = "101_goblin_drops"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "goblin_claim",
            "telegram_user_id",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
        )
    else:
        with op.batch_alter_table("goblin_claim") as batch:
            batch.alter_column(
                "telegram_user_id",
                existing_type=sa.Integer(),
                type_=sa.BigInteger(),
                existing_nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "goblin_claim",
            "telegram_user_id",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
