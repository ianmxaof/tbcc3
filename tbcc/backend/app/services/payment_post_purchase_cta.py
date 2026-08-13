"""Post-purchase cross-sell keyboards — moment-of-delight ladder after Stars checkout."""

from __future__ import annotations

from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

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

    if kind == "loot_key":
        rows: list[list[dict[str, str]]] = []
        if intro:
            rows.append([{"text": "⭐ VIP Intro — skip gates", "url": intro}])
        if companion:
            rows.append([{"text": "🔥 Free spicy reveal", "url": companion}])
        return rows

    if kind == "bundle":
        rows = []
        if loot:
            rows.append([{"text": "🎲 Loot God — free roll", "url": loot}])
        if companion:
            rows.append([{"text": "🔥 Spicy AI reveal", "url": companion}])
        return rows

    rows = []
    if loot:
        rows.append([{"text": "🎲 Loot God — free roll", "url": loot}])
    if companion:
        rows.append([{"text": "🔥 Spicy AI reveal", "url": companion}])
    return rows


def post_purchase_cross_sell_html(kind: str) -> str:
    if kind == "loot_key":
        return "<b>While your key is active</b> — VIP unlocks daily god rolls + all lanes."
    if kind == "bundle":
        return "<b>Your pack is ready.</b> Stack a free loot roll or spicy reveal next."
    return "<b>Welcome to VIP.</b> Try a free loot roll or spicy reveal while you're here."


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
