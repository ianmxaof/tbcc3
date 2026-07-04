"""Inline controls shown during loot roll delivery (mirrors loot_bot menu)."""

from __future__ import annotations

import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

_DEFAULT_FREE_PULL_LIMIT = 5


def roll_action_label(
    *,
    free_pull_number: int = 0,
    free_pulls_remaining: int | None = None,
    free_pull_limit: int = _DEFAULT_FREE_PULL_LIMIT,
) -> str:
    """Roll now for first pull; Roll again N/5 once the lesson chain has started."""
    limit = max(1, int(free_pull_limit or _DEFAULT_FREE_PULL_LIMIT))
    rem = free_pulls_remaining
    step = max(0, int(free_pull_number or 0))
    if step <= 0 and (rem is None or rem >= limit):
        return "🎲 Roll now"
    if rem is not None and rem > 0:
        next_n = min(limit, step + 1) if step > 0 else min(limit, limit - rem + 1)
        return f"🎲 Roll again {next_n}/{limit}"
    return "🎲 Roll now"


def build_loot_roll_inline_markup(
    *,
    free_pull_number: int = 0,
    free_pulls_remaining: int | None = None,
    free_pull_limit: int = _DEFAULT_FREE_PULL_LIMIT,
) -> InlineKeyboardMarkup:
    invite = (os.getenv("TBCC_LOOT_ROOM_INVITE_URL") or "").strip()
    pay = (
        os.getenv("TBCC_PAYMENT_BOT_USERNAME")
        or os.getenv("BOT_USERNAME")
        or "aofsubscriptions_bot"
    ).strip().lstrip("@")

    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                roll_action_label(
                    free_pull_number=free_pull_number,
                    free_pulls_remaining=free_pulls_remaining,
                    free_pull_limit=free_pull_limit,
                ),
                callback_data="loot:roll",
            ),
            InlineKeyboardButton("🔗 Referral", callback_data="loot:referral"),
        ],
    ]
    if pay:
        rows.append(
            [
                InlineKeyboardButton("🗝 24h room key", url=f"https://t.me/{pay}?start=loot"),
                InlineKeyboardButton("💳 Payment bot", url=f"https://t.me/{pay}"),
            ]
        )
    if invite:
        rows.append([InlineKeyboardButton("🚪 Loot Room invite", url=invite)])
    rows.append(
        [
            InlineKeyboardButton("📖 Guide", callback_data="loot:guide"),
            InlineKeyboardButton("ℹ️ Menu", callback_data="loot:help"),
        ]
    )
    return InlineKeyboardMarkup(rows)
