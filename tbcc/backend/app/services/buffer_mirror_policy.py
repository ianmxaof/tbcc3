"""Which Telegram channels may trigger Buffer X mirrors."""

from __future__ import annotations

from app.data.aof_network import BANNED_MAIN_GROUP_IDENT, MAIN_GROUP_IDENT


def is_banned_main_telegram_identifier(identifier: str | None) -> bool:
    ident = (identifier or "").strip()
    return bool(ident) and ident == BANNED_MAIN_GROUP_IDENT


def is_loot_room_hub_identifier(identifier: str | None) -> bool:
    return (identifier or "").strip() == MAIN_GROUP_IDENT


def buffer_mirror_allowed_for_telegram_identifier(identifier: str | None) -> bool:
    """Never mirror Buffer from the banned legacy main group."""
    return not is_banned_main_telegram_identifier(identifier)
