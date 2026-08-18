"""Mock modifier tease on free pulls — paid runs get the real attachments."""

from __future__ import annotations

import html
import random
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.loot_free_tutorial import (
    STEP_AFTER_CARD,
    exhausted_hook_html,
    pull_number_from_preview,
    step_progress_label,
)

# Shown as locked examples; not drawn from loot_modifiers.
FREE_PULL_TEASE_LINES: list[tuple[str, str]] = [
    ("local_zip_pack", "Encrypted zip bundle"),
    ("mega_pack", "Mega archive drop"),
    ("telegram_group", "Private group invite"),
    ("telegram_channel", "Channel / sticker pack"),
    ("internal_route", "Vault-side unlock route"),
    ("other", "Extra modifier slot (up to 3 on paid)"),
]

# Which tease lines to highlight per lesson (instructional focus)
_STEP_TEASE_KINDS: dict[int, list[str]] = {
    1: ["telegram_group"],
    2: ["mega_pack"],
    3: ["local_zip_pack", "telegram_group", "other"],
    4: ["mega_pack", "internal_route"],
    5: ["local_zip_pack", "mega_pack", "telegram_group", "other"],
}


def pick_tease_lines(rng: random.Random, count: int = 4, *, step: int = 1) -> list[dict[str, str]]:
    by_kind = {k: label for k, label in FREE_PULL_TEASE_LINES}
    preferred = _STEP_TEASE_KINDS.get(step) or []
    out: list[dict[str, str]] = []
    for kind in preferred:
        if kind in by_kind and len(out) < count:
            out.append({"kind": kind, "label": by_kind[kind], "locked": True})
    pool = [x for x in FREE_PULL_TEASE_LINES if x[0] not in {d["kind"] for d in out}]
    rng.shuffle(pool)
    for kind, label in pool:
        if len(out) >= count:
            break
        out.append({"kind": kind, "label": label, "locked": True})
    return out


def build_free_pull_tease_html(
    preview: dict[str, Any],
    *,
    free_pulls_remaining: int,
    payment_bot_username: str | None = None,
) -> str:
    step = pull_number_from_preview(preview)
    lines = preview.get("tease_modifiers") or pick_tease_lines(random.Random(), count=4, step=step)
    progress = html.escape(step_progress_label(preview))
    face = lines[:4]
    bullet = "\n".join(
        f"▣ <s>{html.escape(str(x.get('label') or 'modifier'))}</s>"
        for x in face
    )

    rem = max(0, int(free_pulls_remaining))
    after = html.escape(STEP_AFTER_CARD.get(step, ""))

    if rem <= 0:
        return exhausted_hook_html(payment_bot_username=payment_bot_username)

    next_line = (
        f"<i>{rem} complimentary pull(s) left — keep rolling to finish the lesson.</i>"
        if rem > 1
        else "<i>One free pull left after this — then the full table opens with a 24h key.</i>"
    )

    return (
        f"<b>{progress}</b> · <i>Incomplete crate — 4 of 5 face-up</i>\n"
        "▣ ▣ ▣ ▣ 🔒\n"
        "Four tiles are paid-table <b>examples</b> (crossed out on purpose). "
        "The fifth tile is <b>not a hidden roll</b> — it stays face-down until a 24h Origin key.\n\n"
        f"{bullet}\n"
        "🔒 <b>Tile 5</b> — Origin key (full album + real modifiers)\n\n"
        f"{after}\n"
        f"{next_line}"
    )


def crate_origin_key_markup(
    *,
    payment_bot_username: str | None = None,
    loot_bot_username: str | None = None,
) -> InlineKeyboardMarkup:
    """Origin key (Stars checkout) + loot_free deep link (src_loot_free)."""
    import os

    pay = (payment_bot_username or os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "aofsubscriptions_bot").strip().lstrip("@")
    loot = (loot_bot_username or os.getenv("TBCC_LOOT_BOT_USERNAME") or "aof_lootgod_bot").strip().lstrip("@")
    rows: list[list[InlineKeyboardButton]] = []
    if pay:
        rows.append(
            [InlineKeyboardButton("🗝 Origin key — unlock tile 5", url=f"https://t.me/{pay}?start=loot")]
        )
    if loot:
        rows.append(
            [InlineKeyboardButton("🎲 Open crate (loot_free)", url=f"https://t.me/{loot}?start=loot_free")]
        )
    return InlineKeyboardMarkup(rows)


def build_vip_daily_tease_html(preview: dict[str, Any]) -> str:
    """Footer after VIP daily god roll — distinct from complimentary 5-pull lesson."""
    tier = preview.get("rarity_tier") or "?"
    lines = preview.get("tease_modifiers") or []
    bullet = "\n".join(
        f"• <s>{html.escape(str(x.get('label') or 'modifier'))}</s>"
        for x in lines
    )
    return (
        f"<b>VIP god roll</b> · tier {html.escape(str(tier))}\n"
        "High-tier daily perk for AOF VIP — one pull per UTC day.\n"
        "Paid room runs still unlock real modifiers on your table.\n\n"
        f"{bullet}\n\n"
        "<i>Back tomorrow for another /viproll — weekly mega drops in the VIP channel.</i>"
    )
