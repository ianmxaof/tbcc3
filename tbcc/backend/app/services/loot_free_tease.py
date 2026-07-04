"""Mock modifier tease on free pulls — paid runs get the real attachments."""

from __future__ import annotations

import html
import random
from typing import Any

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


def pick_tease_lines(rng: random.Random, count: int = 3, *, step: int = 1) -> list[dict[str, str]]:
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
    lines = preview.get("tease_modifiers") or pick_tease_lines(random.Random(), count=3, step=step)
    progress = html.escape(step_progress_label(preview))

    bullet = "\n".join(
        f"• <s>{html.escape(str(x.get('label') or 'modifier'))}</s>"
        for x in lines
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
        f"<b>{progress}</b> · <i>Paid-table preview (locked on free)</i>\n"
        "These lines are <b>intentionally crossed out</b> — not broken rewards. "
        "They show what a <b>24h room run</b> can attach after your album.\n\n"
        f"{bullet}\n\n"
        f"{after}\n"
        f"{next_line}"
    )


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
