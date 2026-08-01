#!/usr/bin/env python3
"""Post Loot creator recruitment copy (Variation G) to AOF LOOT ROOM.

  python scripts/post_loot_creator_recruitment.py --dry-run
  python scripts/post_loot_creator_recruitment.py --execute
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.aof_network import MAIN_GROUP_IDENT
from app.services.telegram_bot_markup import send_message_with_inline_keyboard

VARIATION_G_HTML = (
    "<b>✨ CREATOR REVEAL BOARD</b> · <i>Loot Room modifier pool</i>\n\n"
    "<b>UNDRESS · CREATOR FUNNEL</b> · TOP · "
    '<a href="https://telegram.me/aof_lootgod_bot">LOOT</a> · '
    '<a href="https://telegram.me/aofmainhub">HUB</a>\n\n'
    "<blockquote>✓ OF · Fansly · ManyVids · Fanvue\n"
    "✓ Privacy · LoyalFans · SextPanther · SextingFinder\n"
    "✓ Linktree · allmylinks · Beacons · Telegram\n"
    "✓ Snapchat · Kik · MV · Patreon</blockquote>\n\n"
    "<b>Command</b> (tap to copy in DM):\n"
    "<pre>/model</pre>\n\n"
    '<blockquote expandable>⚠️ <b>Operator review</b> — gate links and redirects are '
    "rejected. Paste your <i>public profile URL</i> only. Approved creators can appear "
    "in up to <b>3 bonus slots</b> on tier 5+ LootAlbum captions.</blockquote>\n\n"
    "<tg-spoiler>What rollers see: your display name + one clean link under a high-tier "
    "roll — not spammed in the main channel.</tg-spoiler>"
)


def _loot_bot_username() -> str:
    return (os.getenv("TBCC_LOOT_BOT_USERNAME") or "aof_lootgod_bot").strip().lstrip("@")


def _keyboard() -> list[list[dict[str, str]]]:
    un = _loot_bot_username()
    return [
        [{"text": "📦 Open Creator promo in DM", "url": f"https://t.me/{un}?start=model"}],
        [
            {"text": "🎲 Free rolls", "url": f"https://t.me/{un}?start=loot_free"},
            {"text": "🔗 Link hub", "url": "https://telegram.me/aofmainhub"},
        ],
    ]


async def _post(chat_id: str, *, execute: bool) -> dict:
    payload = {
        "chat": chat_id,
        "variant": "G",
        "text_preview": VARIATION_G_HTML[:200] + "…",
        "buttons": _keyboard(),
    }
    if not execute:
        return {**payload, "ok": True, "dry_run": True}
    mid = await send_message_with_inline_keyboard(
        chat_id,
        text=VARIATION_G_HTML,
        buttons_data=_keyboard(),
        parse_mode="HTML",
    )
    if not mid:
        return {**payload, "ok": False, "error": "sendMessage failed — payment bot admin in Loot Room?"}
    return {**payload, "ok": True, "message_id": mid, "method": "payment_bot"}


def main() -> int:
    p = argparse.ArgumentParser(description="Post creator recruitment Variation G to Loot Room")
    p.add_argument("--chat", default=MAIN_GROUP_IDENT, help="Loot Room chat id (default MAIN_GROUP)")
    p.add_argument("--execute", action="store_true", help="Actually post via payment bot")
    args = p.parse_args()
    execute = bool(args.execute)
    report = asyncio.run(_post(args.chat, execute=execute))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
