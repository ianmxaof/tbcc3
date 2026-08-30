"""Post-purchase cross-sell keyboards — moment-of-delight ladder after Stars checkout."""

from __future__ import annotations

from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.data.aof_vip_membership import vip_display_name
from app.services.aof_social_links import (
    companion_bot_username,
    loot_free_start_url,
    payment_bot_username,
)


def classify_post_purchase_kind(*, is_bundle: bool, sub: dict[str, Any]) -> str:
    if is_bundle or (str(sub.get("plan_product_type") or "").strip().lower() == "bundle"):
        return "bundle"
    section = str(sub.get("bot_section") or "main").strip().lower()
    if section == "loot":
        return "loot_key"
    return "vip_sub"


def post_purchase_inline_keyboard_rows(kind: str) -> list[list[dict[str, str]]]:
    pay = payment_bot_username()
    loot = loot_free_start_url()
    companion_un = companion_bot_username()
    companion = f"https://telegram.me/{companion_un}" if companion_un else ""
    subscribe = f"https://t.me/{pay}?start=subscribe" if pay else ""
    intro = f"https://t.me/{pay}?start=cm10" if pay else subscribe
    from app.services.bot_network_discovery import network_deep_link_url

    network = network_deep_link_url()

    if kind == "loot_key":
        rows: list[list[dict[str, str]]] = []
        if network:
            rows.append([{"text": "🌐 Explore AOF network", "url": network}])
        if intro:
            rows.append([{"text": f"⭐ {vip_display_name()} Intro — skip gates", "url": intro}])
        if companion:
            rows.append([{"text": "🔥 Free spicy reveal", "url": companion}])
        return rows

    if kind == "bundle":
        rows = []
        if network:
            rows.append([{"text": "🌐 Explore AOF network", "url": network}])
        if loot:
            rows.append([{"text": "🎲 Loot God — free roll", "url": loot}])
        if companion:
            rows.append([{"text": "🔥 Spicy AI reveal", "url": companion}])
        return rows

    rows = []
    if network:
        rows.append([{"text": "🌐 Explore AOF network", "url": network}])
    if loot:
        rows.append([{"text": "🎲 Loot God — free roll", "url": loot}])
    if companion:
        rows.append([{"text": "🔥 Spicy AI reveal", "url": companion}])
    return rows


def post_purchase_cross_sell_html(kind: str) -> str:
    tier = vip_display_name()
    if kind == "loot_key":
        return f"<b>While your key is active</b> — {tier} unlocks daily god rolls + all lanes."
    if kind == "bundle":
        return "<b>Your pack is ready.</b> Stack a free loot roll or spicy reveal next."
    return f"<b>Welcome to the {tier}.</b> Try a free loot roll or spicy reveal while you're here."


def post_purchase_inline_keyboard(kind: str) -> InlineKeyboardMarkup | None:
    rows = post_purchase_inline_keyboard_rows(kind)
    if not rows:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text=btn["text"], url=btn["url"]) for btn in row] for row in rows]
    )


def post_purchase_reply_markup(kind: str) -> dict[str, Any] | None:
    rows = post_purchase_inline_keyboard_rows(kind)
    if not rows:
        return None
    return {"inline_keyboard": rows}
