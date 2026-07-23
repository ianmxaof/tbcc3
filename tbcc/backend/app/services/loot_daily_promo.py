"""Copy + Telegram payload for daily Loot Room promo in the main AOF group."""

from __future__ import annotations

import html
import os
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
        pay_un = (
            (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "").strip().lstrip("@")
            or "aofsubscriptions_bot"
        )
        intro = (
            "<b>Loot Room — 24h access via Stars.</b>\n\n"
            "Tiered pulls. Modifier slots. Nothing guaranteed.\n"
            f'Paid room key: <a href="https://t.me/{html.escape(pay_un, quote=True)}?start=loot">@{html.escape(pay_un)}</a> → /loot\n'
            f"Free tasters: @{bot_user} → /roll (5 lifetime pulls per account)."
        )

    tail = (
        f"\n\n→ @{bot_user}"
        f"{invite_line}"
    )
    return f"{intro}{tail}"


def loot_daily_promo_inline_keyboard(bot_username: str, *, payment_bot_username: str | None = None) -> dict[str, Any]:
    """Deep link: paid checkout → payment bot; free pull → loot overseer."""
    loot_un = str(bot_username or "aof_lootgod_bot").strip().lstrip("@")
    pay_un = (
        (payment_bot_username or "").strip().lstrip("@")
        or (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "").strip().lstrip("@")
    )
    rows: list[list[dict[str, str]]] = []
    if pay_un:
        rows.append([{"text": "24h room access (Stars)", "url": f"https://t.me/{pay_un}?start=loot"}])
    else:
        rows.append([{"text": "24h room access", "url": f"https://t.me/{loot_un}?start=loot_keys"}])
    rows.append([{"text": "Claim free pull", "url": f"https://telegram.me/{loot_un}"}])
    return {"inline_keyboard": rows}
