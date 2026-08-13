"""Companion exhaustion CTAs — route Undress funnel users to AOF loot + VIP."""

from __future__ import annotations

import html
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.aof_social_links import loot_bot_username, payment_bot_username


def loot_free_cta_url() -> str:
    un = loot_bot_username()
    return f"https://t.me/{un}?start=loot_free" if un else ""


def vip_checkout_cta_url() -> str:
    un = payment_bot_username()
    return f"https://t.me/{un}?start=subscribe" if un else ""


def companion_exhaustion_inline_keyboard_rows() -> list[list[dict[str, str]]]:
    """Bot API reply_markup rows."""
    rows: list[list[dict[str, str]]] = []
    loot = loot_free_cta_url()
    vip = vip_checkout_cta_url()
    if loot:
        rows.append([{"text": "🎲 Loot God — free rolls", "url": loot}])
    if vip:
        rows.append([{"text": "⭐ AOF VIP — skip gates", "url": vip}])
    return rows


def companion_exhaustion_inline_keyboard() -> InlineKeyboardMarkup | None:
    rows = companion_exhaustion_inline_keyboard_rows()
    if not rows:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text=btn["text"], url=btn["url"]) for btn in row] for row in rows]
    )


def companion_exhaustion_reply_markup() -> dict[str, Any] | None:
    rows = companion_exhaustion_inline_keyboard_rows()
    if not rows:
        return None
    return {"inline_keyboard": rows}


def companion_exhaustion_cta_html(*, include_undress: bool = False, undress_url: str = "") -> str:
    loot = loot_free_cta_url()
    vip = vip_checkout_cta_url()
    parts = [
        "<b>Want more on AOF?</b>",
    ]
    if loot:
        parts.append(f'🎲 <a href="{html.escape(loot, quote=True)}">Loot God</a> — free rolls, then keys')
    if vip:
        parts.append(f'⭐ <a href="{html.escape(vip, quote=True)}">VIP</a> — skip gates, bigger drops')
    if include_undress and undress_url:
        parts.append(f'💰 <a href="{html.escape(undress_url, quote=True)}">More AI credits</a> (your ref)')
    return "\n".join(parts)
