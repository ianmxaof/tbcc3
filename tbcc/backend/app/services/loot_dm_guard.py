"""Loot bot interactions are DM-only — redirect group/channel taps to private chat."""

from __future__ import annotations

import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def loot_dm_only_enabled() -> bool:
    raw = (os.getenv("TBCC_LOOT_DM_ONLY") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def should_redirect_loot_to_dm(*, chat_type: str | None) -> bool:
    if not loot_dm_only_enabled():
        return False
    return (chat_type or "").lower() != "private"


def loot_dm_deep_link(*, bot_username: str, start: str = "loot_free") -> str:
    un = (bot_username or "aof_lootgod_bot").strip().lstrip("@")
    payload = (start or "loot_free").strip()
    return f"https://t.me/{un}?start={payload}"


def loot_dm_redirect_markup(*, bot_username: str, start: str = "loot_free") -> InlineKeyboardMarkup:
    url = loot_dm_deep_link(bot_username=bot_username, start=start)
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🎲 Open Loot God in DM", url=url)]]
    )


def loot_dm_redirect_html(*, bot_username: str) -> str:
    un = (bot_username or "aof_lootgod_bot").strip().lstrip("@")
    return (
        "<b>Loot rolls are DM-only</b> — not in group topics.\n\n"
        f'Tap below to continue with <a href="https://t.me/{un}?start=loot_free">@{un}</a> privately.'
    )
