"""Companion bot gate health — Bot API channel-admin probe for ops alerts."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from app.services.companion_access import gate_enabled, network_channel_idents

logger = logging.getLogger(__name__)

_CACHE: dict[str, Any] = {}
_CACHE_TTL_SEC = 300.0


def _companion_bot_token() -> str:
    return (os.getenv("TBCC_COMPANION_BOT_TOKEN") or os.getenv("COMPANION_BOT_TOKEN") or "").strip()


def _bot_admin_status(membership: dict[str, Any]) -> bool:
    if not membership.get("ok"):
        return False
    result = membership.get("result") or {}
    return str(result.get("status") or "").lower() in ("administrator", "creator")


async def probe_companion_bot_channel_admin(*, force: bool = False) -> dict[str, Any]:
    """
    True when @aof_spicybot_bot is administrator in every AOF network channel.
    Membership verification (getChatMember for users) only works in channels the bot can see.
    """
    now = time.monotonic()
    if not force and _CACHE and now - float(_CACHE.get("checked_at_mono") or 0) < _CACHE_TTL_SEC:
        return dict(_CACHE)

    token = _companion_bot_token()
    if not token:
        out = {
            "ok": False,
            "gate_enabled": gate_enabled(),
            "error": "TBCC_COMPANION_BOT_TOKEN unset",
            "bot_admin_all_channels": False,
            "channel_count": len(network_channel_idents()),
            "missing_channels": [],
        }
        _CACHE.clear()
        _CACHE.update(out)
        _CACHE["checked_at_mono"] = now
        return out

    base = f"https://api.telegram.org/bot{token}"
    missing: list[dict[str, str]] = []
    probes: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        me = (await client.get(f"{base}/getMe")).json()
        if not me.get("ok"):
            out = {
                "ok": False,
                "gate_enabled": gate_enabled(),
                "error": f"getMe failed: {me}",
                "bot_admin_all_channels": False,
                "channel_count": len(network_channel_idents()),
                "missing_channels": [],
            }
            _CACHE.clear()
            _CACHE.update(out)
            _CACHE["checked_at_mono"] = now
            return out
        bot_id = int(me["result"]["id"])

        for key, ident, display_name in network_channel_idents():
            chat_id = int(ident) if ident.lstrip("-").isdigit() else ident
            resp = await client.get(
                f"{base}/getChatMember",
                params={"chat_id": chat_id, "user_id": bot_id},
            )
            data = resp.json()
            admin_ok = _bot_admin_status(data)
            row = {
                "key": key,
                "ident": ident,
                "display_name": display_name,
                "bot_admin": admin_ok,
                "telegram_ok": bool(data.get("ok")),
                "status": (data.get("result") or {}).get("status"),
                "description": data.get("description"),
            }
            probes.append(row)
            if not admin_ok:
                missing.append(
                    {
                        "key": key,
                        "ident": ident,
                        "display_name": display_name,
                        "reason": str(data.get("description") or row.get("status") or "not_admin"),
                    }
                )

    all_ok = len(missing) == 0 and len(probes) > 0
    out = {
        "ok": True,
        "gate_enabled": gate_enabled(),
        "bot_admin_all_channels": all_ok,
        "channel_count": len(probes),
        "admin_channel_count": len(probes) - len(missing),
        "missing_channels": missing,
        "probes": probes,
    }
    _CACHE.clear()
    _CACHE.update(out)
    _CACHE["checked_at_mono"] = now
    if not all_ok and gate_enabled():
        logger.warning(
            "companion gate: bot not admin in %d/%d channels — membership verify will fail outside Loot Room commons",
            len(missing),
            len(probes),
        )
    return out


def probe_companion_bot_channel_admin_sync(*, force: bool = False) -> dict[str, Any]:
    import asyncio
    import concurrent.futures

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(probe_companion_bot_channel_admin(force=force))

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(
            lambda: asyncio.run(probe_companion_bot_channel_admin(force=force))
        ).result()
