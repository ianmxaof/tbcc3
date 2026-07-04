#!/usr/bin/env python3
"""Invite + promote @aof_spicybot_bot in AOF network channels (for getChatMember gate)."""

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

import httpx
from telethon.tl.functions.channels import EditAdminRequest, InviteToChannelRequest
from telethon.tl.types import ChatAdminRights

from app.data.aof_network import AOF_NETWORK_CHANNELS, MAIN_GROUP_IDENT
from app.services.companion_access import network_channel_idents
from app.services.telegram_admin import run_telegram_client_io
from app.utils.telegram_peer import normalize_telethon_peer_identifier

_IDENT_TO_INVITE: dict[str, str] = {MAIN_GROUP_IDENT: ""}
for _ch in AOF_NETWORK_CHANNELS:
    _IDENT_TO_INVITE.setdefault(_ch.identifier, _ch.invite)


def _bot_username() -> str:
    return (os.getenv("TBCC_COMPANION_BOT_USERNAME") or "aof_spicybot_bot").lstrip("@")


def _bot_token() -> str:
    return (os.getenv("TBCC_COMPANION_BOT_TOKEN") or "").strip()


async def _probe_bot_api(channel_ident: str, admin_uid: int | None) -> dict:
    token = _bot_token()
    if not token:
        return {"error": "TBCC_COMPANION_BOT_TOKEN unset"}
    base = f"https://api.telegram.org/bot{token}"
    out: dict = {"channel": channel_ident}
    async with httpx.AsyncClient(timeout=30.0) as client:
        me = (await client.get(f"{base}/getMe")).json()
        if not me.get("ok"):
            out["bot"] = {"error": me}
            return out
        bot_id = me["result"]["id"]
        out["bot"] = {"id": bot_id, "username": me["result"].get("username")}

        chat_id = int(channel_ident) if channel_ident.lstrip("-").isdigit() else channel_ident
        adm = await client.get(
            f"{base}/getChatMember",
            params={"chat_id": chat_id, "user_id": bot_id},
        )
        out["bot_membership"] = adm.json()

        if admin_uid:
            user_chk = await client.get(
                f"{base}/getChatMember",
                params={"chat_id": chat_id, "user_id": admin_uid},
            )
            out["admin_probe"] = user_chk.json()
    return out


async def _resolve_channel(client, channel_ident: str):
    peer = normalize_telethon_peer_identifier(channel_ident)
    try:
        return await client.get_input_entity(peer)
    except Exception:
        invite = (_IDENT_TO_INVITE.get(channel_ident) or "").strip()
        if invite:
            return await client.get_input_entity(invite)
        raise


async def _promote_bot_in_channel(client, channel_ident: str, bot_username: str) -> dict:
    try:
        channel = await _resolve_channel(client, channel_ident)
    except Exception as e:
        return {
            "channel": channel_ident,
            "error": f"resolve failed: {e!s}"[:300],
            "hint": "Admin Telethon account must be in the channel, or add the bot manually in Telegram channel settings.",
        }
    bot = await client.get_input_entity(bot_username)
    rights = ChatAdminRights(
        change_info=False,
        post_messages=False,
        edit_messages=False,
        delete_messages=False,
        ban_users=False,
        invite_users=True,
        pin_messages=False,
        add_admins=False,
        anonymous=False,
        manage_call=False,
        other=True,
    )
    try:
        await client(InviteToChannelRequest(channel, [bot]))
    except Exception as e:
        if "already" not in str(e).lower():
            return {"channel": channel_ident, "invite": "skipped", "detail": str(e)[:200]}
    await client(
        EditAdminRequest(
            channel=channel,
            user_id=bot,
            admin_rights=rights,
            rank="Companion bot",
        )
    )
    return {"channel": channel_ident, "status": "promoted"}


async def _run_execute(bot_username: str, *, only_channel: str | None = None) -> list[dict]:
    idents = {MAIN_GROUP_IDENT}
    idents.update(ch.identifier for ch in AOF_NETWORK_CHANNELS)
    if only_channel:
        idents = {only_channel}

    async def _work(client):
        results = []
        for ident in sorted(idents):
            try:
                results.append(await _promote_bot_in_channel(client, ident, bot_username))
            except Exception as e:
                results.append({"channel": ident, "error": str(e)[:300]})
        return results

    return await run_telegram_client_io(_work)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure companion bot is admin in AOF channels")
    parser.add_argument("--execute", action="store_true", help="Invite + promote via Telethon admin session")
    parser.add_argument("--probe", action="store_true", help="Bot API getChatMember probe (default)")
    parser.add_argument("--channel", help="Single channel ident to probe/promote")
    parser.add_argument("--admin-uid", type=int, help="Telegram user id to probe getChatMember for")
    args = parser.parse_args()

    bot_username = _bot_username()
    report: dict = {"bot_username": bot_username, "channels": network_channel_idents()}

    if args.probe or not args.execute:
        admin_uid = args.admin_uid
        if admin_uid is None:
            raw = (os.getenv("ADMIN_TELEGRAM_ID") or "").strip().split(",")[0].strip()
            if raw.isdigit():
                admin_uid = int(raw)
        targets = [args.channel] if args.channel else [ident for _k, ident, _n in network_channel_idents()]
        probes = []
        for ident in targets:
            probes.append(asyncio.run(_probe_bot_api(ident, admin_uid)))
        report["probes"] = probes

    if args.execute:
        report["promote"] = asyncio.run(_run_execute(bot_username, only_channel=args.channel))

    report["manual_fallback"] = (
        "If Telethon cannot resolve channels: Telegram → each AOF channel → "
        "Manage → Administrators → Add @aof_spicybot_bot (no post rights needed)."
    )

    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
