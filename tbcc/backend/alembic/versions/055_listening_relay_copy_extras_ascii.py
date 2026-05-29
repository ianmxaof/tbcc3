"""Listening relay: copy-panel scheduler parity, ASCII library, rotation modes."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "055_relay_copy_ascii"
down_revision: Union[str, None] = "054_zip_bundle_promo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Columns may already exist from main.py startup migrations (Postgres dev parity).
_NEW_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    (
        "template_rotation_mode",
        sa.Column("template_rotation_mode", sa.String(16), nullable=False, server_default="sequential"),
    ),
    ("message_slot_extras_json", sa.Column("message_slot_extras_json", sa.Text(), nullable=True)),
    (
        "ascii_art_enabled",
        sa.Column("ascii_art_enabled", sa.Boolean(), nullable=False, server_default="0"),
    ),
    (
        "ascii_art_min_interval",
        sa.Column("ascii_art_min_interval", sa.Integer(), nullable=False, server_default="3"),
    ),
    (
        "ascii_art_max_interval",
        sa.Column("ascii_art_max_interval", sa.Integer(), nullable=False, server_default="6"),
    ),
    (
        "ascii_art_scrobble_counter",
        sa.Column("ascii_art_scrobble_counter", sa.Integer(), nullable=False, server_default="0"),
    ),
    ("ascii_art_next_threshold", sa.Column("ascii_art_next_threshold", sa.Integer(), nullable=True)),
    ("ascii_art_library_json", sa.Column("ascii_art_library_json", sa.Text(), nullable=True)),
    (
        "tryptych_enabled",
        sa.Column("tryptych_enabled", sa.Boolean(), nullable=False, server_default="0"),
    ),
    (
        "tryptych_on_ascii_beat",
        sa.Column("tryptych_on_ascii_beat", sa.Boolean(), nullable=False, server_default="1"),
    ),
)


def _existing_columns() -> set[str]:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "listening_relay_settings" not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns("listening_relay_settings")}


def upgrade() -> None:
    cols = _existing_columns()
    if not cols:
        return
    for name, col in _NEW_COLUMNS:
        if name not in cols:
            op.add_column("listening_relay_settings", col)


def downgrade() -> None:
    cols = _existing_columns()
    for name, _ in reversed(_NEW_COLUMNS):
        if name in cols:
            op.drop_column("listening_relay_settings", name)
