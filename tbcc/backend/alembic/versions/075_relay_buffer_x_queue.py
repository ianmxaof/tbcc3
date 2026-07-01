"""Listening relay buffer_x_queue for armed X captions."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "075_relay_buffer_x_queue"
down_revision: Union[str, None] = "074_watermark_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("listening_relay_settings", "buffer_x_queue_json"):
        op.add_column("listening_relay_settings", sa.Column("buffer_x_queue_json", sa.Text(), nullable=True))


def downgrade() -> None:
    if _has_column("listening_relay_settings", "buffer_x_queue_json"):
        op.drop_column("listening_relay_settings", "buffer_x_queue_json")
