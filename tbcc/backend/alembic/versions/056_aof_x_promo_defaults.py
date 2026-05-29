"""Seed default AOF X promo copy (caption library + listening relay Buffer copy blocks)

Revision ID: 056_aof_x_promo_defaults
Revises: 055_relay_copy_ascii
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "056_aof_x_promo_defaults"
down_revision: Union[str, None] = "055_relay_copy_ascii"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.database.session import SessionLocal
    from app.services.seed_aof_x_promo_defaults import seed_aof_x_promo_defaults

    db = SessionLocal()
    try:
        seed_aof_x_promo_defaults(db)
    finally:
        db.close()


def downgrade() -> None:
    from app.data.aof_x_promo_defaults import AOF_X_PROMO_DEFAULTS

    conn = op.get_bind()
    inspector = inspect(conn)
    if "caption_snippets" in inspector.get_table_names():
        for item in AOF_X_PROMO_DEFAULTS:
            conn.execute(
                sa.text("DELETE FROM caption_snippets WHERE title = :t"),
                {"t": item["title"]},
            )

    if "listening_relay_settings" not in inspector.get_table_names():
        return
    bodies = [d["body"].strip() for d in AOF_X_PROMO_DEFAULTS]
    bodies_json = json.dumps(bodies)
    conn.execute(
        sa.text(
            "UPDATE listening_relay_settings SET message_copy_block_variations = NULL "
            "WHERE id = 1 AND message_copy_block_variations = :j"
        ),
        {"j": bodies_json},
    )
