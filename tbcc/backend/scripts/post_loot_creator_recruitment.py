#!/usr/bin/env python3
"""Post Loot creator recruitment copy to AOF LOOT ROOM (or any chat).

  python scripts/post_loot_creator_recruitment.py --dry-run
  python scripts/post_loot_creator_recruitment.py --variant V4_REVEAL --execute
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.aof_network import MAIN_GROUP_IDENT
from app.services.loot_creator_recruitment_posts import (
    ALL_VARIANTS,
    build_creator_recruitment_html,
    creator_recruitment_keyboard,
)
from app.services.telegram_bot_markup import send_message_with_inline_keyboard


async def _post(chat_id: str, *, variant: str, execute: bool) -> dict:
    html = build_creator_recruitment_html(variant=variant)  # type: ignore[arg-type]
    keyboard = creator_recruitment_keyboard()
    payload = {
        "chat": chat_id,
        "variant": variant,
        "text_preview": html[:200] + "…",
        "buttons": keyboard,
    }
    if not execute:
        return {**payload, "ok": True, "dry_run": True}
    mid = await send_message_with_inline_keyboard(
        chat_id,
        text=html,
        buttons_data=keyboard,
        parse_mode="HTML",
    )
    if not mid:
        return {**payload, "ok": False, "error": "sendMessage failed — payment bot admin in target chat?"}
    return {**payload, "ok": True, "message_id": mid, "method": "payment_bot"}


def main() -> int:
    p = argparse.ArgumentParser(description="Post creator recruitment to Loot Room or lane")
    p.add_argument("--chat", default=MAIN_GROUP_IDENT, help="Target chat id")
    p.add_argument("--variant", choices=list(ALL_VARIANTS), default="G")
    p.add_argument("--execute", action="store_true", help="Actually post via payment bot")
    args = p.parse_args()
    report = asyncio.run(_post(args.chat, variant=args.variant, execute=bool(args.execute)))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
