"""Mock modifier tease on free pulls — paid runs get the real attachments."""

from __future__ import annotations

import html
import random
from typing import Any

# Shown as locked examples; not drawn from loot_modifiers.
FREE_PULL_TEASE_LINES: list[tuple[str, str]] = [
    ("local_zip_pack", "Encrypted zip bundle + injected promo"),
    ("mega_pack", "Mega archive drop"),
    ("telegram_group", "Private group invite"),
    ("telegram_channel", "Sticker / channel pack"),
    ("internal_route", "Vault-side unlock route"),
    ("other", "Multi-slot modifier stack (up to 3)"),
]


def pick_tease_lines(rng: random.Random, count: int = 3) -> list[dict[str, str]]:
    pool = list(FREE_PULL_TEASE_LINES)
    rng.shuffle(pool)
    out: list[dict[str, str]] = []
    for kind, label in pool[: max(1, min(count, len(pool)))]:
        out.append({"kind": kind, "label": label, "locked": True})
    return out


def build_free_pull_tease_html(
    preview: dict[str, Any],
    *,
    free_pulls_remaining: int,
    payment_bot_username: str | None = None,
) -> str:
    lines = preview.get("tease_modifiers") or pick_tease_lines(random.Random())
    bullet = "\n".join(
        f"• <s>{html.escape(str(x.get('label') or 'modifier'))}</s> — paid runs only"
        for x in lines
    )
    pay = (payment_bot_username or "").strip().lstrip("@")
    pay_line = (
        f'\n\n24h room access: <a href="https://t.me/{html.escape(pay)}?start=loot">@{html.escape(pay)}</a> → /loot'
        if pay
        else "\n\n24h room access — payment bot /loot"
    )
    rem = max(0, int(free_pulls_remaining))
    rem_line = f"<i>{rem} free pull(s) left on this account.</i>" if rem else "<b>No free pulls left.</b> Paid room only."
    return (
        "<b>Free table — modifiers locked</b>\n"
        "This pull is one spoiler item, tier-capped, no attachments.\n\n"
        f"{bullet}\n\n"
        f"{rem_line}"
        f"{pay_line}"
    )
