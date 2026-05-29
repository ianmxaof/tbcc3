"""Copy + Telegram payload for daily Loot Room promo in the main AOF group."""

from __future__ import annotations

import html
from typing import Any

from sqlalchemy.orm import Session

from app.services.loot_bot_settings_effective import get_effective_loot_bot_settings


def build_loot_daily_promo_html(db: Session) -> str:
    s = get_effective_loot_bot_settings(db)
    custom = (s.get("daily_promo_intro_html") or "").strip()
    bot_user = html.escape(str(s.get("bot_username") or "aof_lootgod_bot").lstrip("@"))
    invite = (s.get("primary_loot_room_invite_url") or "").strip()
    invite_line = ""
    if invite:
        invite_line = (
            f'\n\nPrivate room: <a href="{html.escape(invite, quote=True)}">Loot Room invite</a>'
        )

    if custom:
        intro = custom
    else:
        intro = (
            "<b>Loot Room — open.</b>\n\n"
            "Tiered pulls. Modifier slots. Nothing guaranteed.\n"
            "@aof_lootgod_bot runs the table — up to five complimentary pulls per account (/roll), then paid 24h room access."
        )

    tail = (
        f"\n\n→ @{bot_user}"
        f"{invite_line}"
    )
    return f"{intro}{tail}"


def loot_daily_promo_inline_keyboard(bot_username: str, *, payment_bot_username: str | None = None) -> dict[str, Any]:
    """Deep link: free pull → loot overseer; paid keys → payment bot."""
    import os

    loot_un = str(bot_username or "aof_lootgod_bot").strip().lstrip("@")
    pay_un = (
        (payment_bot_username or "").strip().lstrip("@")
        or (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "").strip().lstrip("@")
    )
    rows: list[list[dict[str, str]]] = [
        [{"text": "Claim free pull", "url": f"https://t.me/{loot_un}?start=loot_free"}],
    ]
    if pay_un:
        rows.append([{"text": "24h room access", "url": f"https://t.me/{pay_un}?start=loot"}])
    else:
        rows.append([{"text": "24h room access", "url": f"https://t.me/{loot_un}?start=loot_keys"}])
    return {"inline_keyboard": rows}
