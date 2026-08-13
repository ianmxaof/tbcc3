#!/usr/bin/env python3
"""Post Stars checkout CTA to legacy AOF Main (-1003206350461).

Order: payment bot (if admin) → admin_poster → admin → admin_import Telethon.

  python scripts/post_banned_main_checkout.py
  python scripts/post_banned_main_checkout.py --execute
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.aof_network import BANNED_MAIN_GROUP_IDENT, BANNED_MAIN_GROUP_INVITE
from app.database.session import SessionLocal
from app.models.channel import Channel
from app.services.aof_growth_hub import resolve_group_access_plan_id
from app.utils.telethon_session import admin_session_stem, import_session_stem, poster_session_stem

CAMPAIGN_START = (os.getenv("TBCC_BANNED_MAIN_CAMPAIGN_START") or "src_banned_main_wk30").strip()


def _caption() -> str:
    return (
        "<b>AOF is still here — 400+ of you never left.</b>\n\n"
        "VIP access + loot keys. Pay in Telegram Stars — tap below.\n\n"
        "<i>One tap checkout. Cancel anytime.</i>"
    )


def _checkout_buttons(db, plan_id: int) -> list[dict]:
    from app.services.aof_vip_checkout import merge_checkout_buttons

    pay = (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "aofsubscriptions_bot").strip().lstrip("@")
    campaign_url = f"https://t.me/{pay}?start={CAMPAIGN_START}"
    base = [{"text": "🗝 Loot key — 150⭐", "url": f"https://t.me/{pay}?start=src_loot_key_wk30"}]
    merged = merge_checkout_buttons(
        base,
        db,
        checkout_stars_enabled=True,
        checkout_stars_plan_id=int(plan_id),
        checkout_button_label="Pay ⭐ VIP — 30d",
        include_bot_fallback=True,
    )
    # Ensure tagged campaign link present even if merge skipped bot row
    urls = {str(b.get("url") or "").lower() for b in merged}
    if campaign_url.lower() not in urls:
        merged.insert(0, {"text": "⭐ VIP checkout", "url": campaign_url})
    return merged


async def _try_payment_bot(chat_id: str, buttons: list[dict], *, execute: bool) -> dict:
    from app.services.telegram_bot_markup import send_message_with_inline_keyboard

    out = {"method": "payment_bot", "chat_id": chat_id}
    if not execute:
        return {**out, "ok": True, "dry_run": True, "buttons": len(buttons)}
    mid = await send_message_with_inline_keyboard(
        chat_id,
        text=_caption(),
        buttons_data=buttons,
        parse_mode="HTML",
    )
    if mid:
        return {**out, "ok": True, "message_id": mid}
    return {**out, "ok": False, "error": "sendMessage rejected (bot may lack admin in legacy main)"}


async def _try_telethon(stem_label: str, stem: str, buttons: list[dict], *, execute: bool) -> dict:
    from telethon import TelegramClient
    from telethon.errors import RPCError

    from app.services.scheduled_post_service import _build_reply_markup
    from app.utils.telegram_peer import resolve_poster_peer

    session_path = stem
    api_id = int((os.getenv("API_ID") or "0").strip() or 0)
    api_hash = (os.getenv("API_HASH") or "").strip()
    out: dict = {"method": "telethon", "session": stem_label, "stem": stem}
    if not api_id or not api_hash:
        return {**out, "ok": False, "error": "API_ID/API_HASH missing"}
    if not Path(f"{stem}.session").is_file():
        return {**out, "ok": False, "error": "session file missing"}

    client = TelegramClient(session_path, api_id, api_hash)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return {**out, "ok": False, "error": "not authorized"}
        me = await client.get_me()
        out["user_id"] = getattr(me, "id", None)
        out["username"] = getattr(me, "username", None)

        peer = await resolve_poster_peer(
            client,
            BANNED_MAIN_GROUP_IDENT,
            invite_fallback=BANNED_MAIN_GROUP_INVITE,
        )
        out["peer_title"] = getattr(peer, "title", str(peer))
        markup = _build_reply_markup(buttons)
        if not execute:
            return {**out, "ok": True, "dry_run": True, "buttons": len(buttons)}

        msg = await client.send_message(
            peer,
            _caption(),
            parse_mode="html",
            buttons=markup,
            link_preview=False,
        )
        return {**out, "ok": True, "message_id": int(getattr(msg, "id", 0) or 0)}
    except RPCError as e:
        return {**out, "ok": False, "error": f"{e.__class__.__name__}: {str(e)[:200]}"}
    except Exception as e:
        return {**out, "ok": False, "error": str(e)[:300]}
    finally:
        await client.disconnect()


def _ensure_channel_row(db) -> None:
    ch = db.query(Channel).filter(Channel.identifier == BANNED_MAIN_GROUP_IDENT).first()
    if ch:
        if not ch.invite_link:
            ch.invite_link = BANNED_MAIN_GROUP_INVITE
        return
    db.add(
        Channel(
            name="AOF MAIN GROUP (legacy)",
            identifier=BANNED_MAIN_GROUP_IDENT,
            invite_link=BANNED_MAIN_GROUP_INVITE,
        )
    )


async def _run(*, plan_id: int, execute: bool) -> dict:
    db = SessionLocal()
    try:
        buttons = _checkout_buttons(db, plan_id)
        if execute:
            _ensure_channel_row(db)
            db.commit()
    finally:
        db.close()

    attempts: list[dict] = []

    r_bot = await _try_payment_bot(BANNED_MAIN_GROUP_IDENT, buttons, execute=execute)
    attempts.append(r_bot)
    if r_bot.get("ok"):
        return {"execute": execute, "target": BANNED_MAIN_GROUP_IDENT, "plan_id": plan_id, "campaign": CAMPAIGN_START, "attempts": attempts}

    for label, stem in (
        ("admin_poster", poster_session_stem()),
        ("admin", admin_session_stem()),
        ("admin_import", import_session_stem()),
    ):
        r = await _try_telethon(label, stem, buttons, execute=execute)
        attempts.append(r)
        if r.get("ok"):
            break

    return {"execute": execute, "target": BANNED_MAIN_GROUP_IDENT, "plan_id": plan_id, "campaign": CAMPAIGN_START, "attempts": attempts}


def main() -> int:
    parser = argparse.ArgumentParser(description="Post checkout CTA to legacy AOF Main group")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--plan-id", type=int, default=0)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        plan_id = int(args.plan_id) or int(resolve_group_access_plan_id(db) or 10)
    finally:
        db.close()

    report = asyncio.run(_run(plan_id=plan_id, execute=args.execute))
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if any(a.get("ok") for a in report.get("attempts", [])) else 1


if __name__ == "__main__":
    raise SystemExit(main())
