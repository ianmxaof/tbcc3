#!/usr/bin/env python3
"""Deploy pinned Loot Room growth menu (interactive PNG + inline buttons).

Bare Loot Room invite + 18+ line live in the caption — not LV-wrapped.

  python scripts/deploy_loot_room_link_menu.py --execute
  python scripts/deploy_loot_room_link_menu.py --execute --variant v5
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

from app.data.aof_network import MAIN_GROUP_IDENT, MAIN_GROUP_INVITE
from app.services.aof_links_hub_menu_variants import LOOT_VARIANTS, build_interactive_menu_post
from app.services.telegram_bot_markup import send_photo_with_inline_keyboard


def _variant_title(variant: str) -> str:
    return {
        "v5": "GROWTH REVEAL",
        "v6": "GROWTH DARK PANEL",
        "v7": "GROWTH MATRIX",
    }.get(variant, variant.upper())


async def _pin_message(chat_id: str, message_id: int) -> dict:
    import httpx

    token = (os.getenv("TBCC_PAYMENT_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token or message_id <= 0:
        return {"ok": False, "reason": "no_token_or_message_id"}
    url = f"https://api.telegram.org/bot{token}/pinChatMessage"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "disable_notification": True,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=payload)
    if r.status_code != 200:
        return {"ok": False, "status": r.status_code, "body": r.text[:300]}
    return {"ok": True}


async def _try_telethon_pin(chat_id: str, message_id: int) -> dict:
    from telethon import TelegramClient
    from telethon.errors import RPCError

    from app.utils.telegram_peer import resolve_poster_peer
    from app.utils.telethon_session import admin_session_stem, import_session_stem, poster_session_stem

    api_id = int((os.getenv("API_ID") or "0").strip() or 0)
    api_hash = (os.getenv("API_HASH") or "").strip()
    for label, stem in (
        ("admin_poster", poster_session_stem()),
        ("admin", admin_session_stem()),
        ("admin_import", import_session_stem()),
    ):
        if not Path(f"{stem}.session").is_file():
            continue
        client = TelegramClient(stem, api_id, api_hash)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                continue
            peer = await resolve_poster_peer(client, chat_id, invite_fallback=MAIN_GROUP_INVITE)
            await client.pin_message(peer, message_id, notify=False)
            return {"ok": True, "method": f"telethon:{label}"}
        except RPCError as e:
            last = f"{e.__class__.__name__}: {str(e)[:200]}"
        except Exception as e:
            last = str(e)[:300]
        finally:
            await client.disconnect()
    return {"ok": False, "error": last if "last" in dir() else "no_session"}


async def _try_telethon_photo(chat_id: str, post: dict) -> dict:
    from telethon import TelegramClient
    from telethon.errors import RPCError

    from app.services.scheduled_post_service import _build_reply_markup
    from app.utils.telegram_peer import resolve_poster_peer
    from app.utils.telethon_session import admin_session_stem, import_session_stem, poster_session_stem

    api_id = int((os.getenv("API_ID") or "0").strip() or 0)
    api_hash = (os.getenv("API_HASH") or "").strip()
    img = Path(post["image"])
    markup = _build_reply_markup(post["keyboard"])
    last = "no session"
    for label, stem in (
        ("admin_poster", poster_session_stem()),
        ("admin", admin_session_stem()),
        ("admin_import", import_session_stem()),
    ):
        if not Path(f"{stem}.session").is_file():
            continue
        client = TelegramClient(stem, api_id, api_hash)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                continue
            peer = await resolve_poster_peer(client, chat_id, invite_fallback=MAIN_GROUP_INVITE)
            msg = await client.send_file(
                peer,
                str(img),
                caption=post["caption"],
                parse_mode="html",
                buttons=markup,
                force_document=False,
            )
            return {"ok": True, "method": f"telethon:{label}", "message_id": int(getattr(msg, "id", 0) or 0)}
        except RPCError as e:
            last = f"{e.__class__.__name__}: {str(e)[:200]}"
        except Exception as e:
            last = str(e)[:300]
        finally:
            await client.disconnect()
    return {"ok": False, "method": "telethon", "error": last}


async def _post_menu(chat_id: str, post: dict, *, execute: bool, pin: bool) -> dict:
    row = {"variant": post["variant"], "title": post["title"]}
    if not execute:
        row.update({"ok": True, "dry_run": True, "image": post["image"]})
        return row
    if not Path(post["image"]).is_file():
        row.update({"ok": False, "error": f"missing image {post['image']}"})
        return row
    mid = await send_photo_with_inline_keyboard(
        chat_id,
        photo_path=post["image"],
        caption=post["caption"],
        buttons_data=post["keyboard"],
    )
    method = "payment_bot"
    if not mid:
        fb = await _try_telethon_photo(chat_id, post)
        if not fb.get("ok"):
            return {**row, **fb}
        mid = int(fb.get("message_id") or 0)
        method = fb.get("method", "telethon")
    row.update({"ok": True, "method": method, "message_id": mid})
    if pin and mid:
        pin_r = await _pin_message(chat_id, mid)
        if not pin_r.get("ok"):
            pin_r = await _try_telethon_pin(chat_id, mid)
        row["pinned"] = pin_r
    return row


def main() -> int:
    p = argparse.ArgumentParser(description="Deploy pinned Loot Room growth menu")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--chat", default=MAIN_GROUP_IDENT)
    p.add_argument("--variant", default="v5", choices=LOOT_VARIANTS)
    p.add_argument("--columns", type=int, default=2)
    p.add_argument("--no-pin", action="store_true", help="Post without pinning")
    args = p.parse_args()

    db = None
    try:
        from app.database.session import SessionLocal

        db = SessionLocal()
    except Exception:
        db = None

    if db is None:
        print(json.dumps({"ok": False, "error": "db_required_for_loot_menu"}, indent=2))
        return 1

    try:
        post_obj = build_interactive_menu_post(db, "loot", args.variant, button_columns=args.columns)
        post = {
            "variant": args.variant,
            "title": _variant_title(args.variant),
            "caption": post_obj.caption_html,
            "keyboard": post_obj.inline_keyboard,
            "image": str(post_obj.image_path),
        }
        result = asyncio.run(
            _post_menu(args.chat, post, execute=args.execute, pin=not args.no_pin)
        )
        report = {"chat": args.chat, "execute": args.execute, "post": result}
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
