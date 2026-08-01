#!/usr/bin/env python3
"""Post interactive LINK HUB menu (PNG + inline URL buttons) to a Telegram chat.

Telegram cannot make regions inside a PNG clickable — this sends the artwork as
sendPhoto and attaches one URL button per lane/affiliate underneath.

  python scripts/post_links_hub_interactive_menu.py --kind channels --variant v1 --dry-run
  python scripts/post_links_hub_interactive_menu.py --kind ai --variant v1 --execute
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

from app.data.aof_network import MAINHUB_CHANNEL_IDENT
from app.database.session import SessionLocal
from app.services.aof_links_hub_menu_variants import build_interactive_menu_post
from app.services.telegram_bot_markup import send_photo_with_inline_keyboard


def main() -> None:
    p = argparse.ArgumentParser(description="Post interactive LINK HUB menu to Telegram")
    p.add_argument("--kind", choices=["channels", "ai"], default="channels")
    p.add_argument("--variant", choices=["v1", "v2", "v3"], default="v1")
    p.add_argument("--chat", default=MAINHUB_CHANNEL_IDENT, help="Telegram chat id (default @aofmainhub)")
    p.add_argument("--columns", type=int, default=2, help="Inline button columns (1-3)")
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--execute", action="store_true", help="Actually post via payment bot")
    args = p.parse_args()
    dry = not args.execute

    db = SessionLocal()
    try:
        post = build_interactive_menu_post(
            db, args.kind, args.variant, button_columns=max(1, min(3, args.columns))
        )
    finally:
        db.close()

    payload = {
        "chat": args.chat,
        "kind": post.kind,
        "variant": post.variant,
        "title": post.title,
        "image": str(post.image_path),
        "caption": post.caption_html,
        "button_rows": len(post.inline_keyboard),
        "buttons": post.inline_keyboard,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    if dry:
        print("\n(dry-run — pass --execute to post)")
        return

    if not post.image_path.is_file():
        raise SystemExit(f"image missing: {post.image_path}")

    async def _run() -> None:
        mid = await send_photo_with_inline_keyboard(
            args.chat,
            photo_path=post.image_path,
            caption=post.caption_html,
            buttons_data=post.inline_keyboard,
        )
        if not mid:
            raise SystemExit("sendPhoto failed — is payment bot admin in this chat?")
        print(f"posted message_id={mid}")

    asyncio.run(_run())


if __name__ == "__main__":
    main()
