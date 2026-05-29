"""
Fetch public channel message view counts via Telethon (admin poster session).

Requires API_ID/API_HASH and TBCC_POSTER_TELEGRAM_SESSION (same as Celery poster).
Channels must be in TBCC `channels` table with resolvable identifiers.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def telethon_stats_configured() -> bool:
    return bool(
        (os.getenv("API_ID") or "").strip()
        and (os.getenv("API_HASH") or "").strip()
    )


def _poster_session_name() -> str:
    return (os.getenv("TBCC_POSTER_TELEGRAM_SESSION") or "admin_poster").strip()


async def fetch_channel_post_stats(
    channel_identifier: str,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Return recent messages with views where Telegram exposes them (channels/supergroups).
    """
    from telethon import TelegramClient
    from telethon.tl.functions.messages import GetMessagesViewsRequest

    ident = (channel_identifier or "").strip()
    if not ident:
        return {"ok": False, "error": "empty channel identifier"}

    session = _poster_session_name()
    client = TelegramClient(session, int(os.environ["API_ID"]), os.environ["API_HASH"])
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        return {"ok": False, "error": "Telethon session not authorized"}

    try:
        entity = await client.get_entity(ident)
        msgs = await client.get_messages(entity, limit=min(max(limit, 1), 50))
        ids = [m.id for m in msgs if m and m.id]
        views_map: dict[int, int] = {}
        if ids:
            try:
                res = await client(
                    GetMessagesViewsRequest(peer=entity, id=ids, increment=False)
                )
                for mid, vc in zip(ids, getattr(res, "views", []) or []):
                    views_map[int(mid)] = int(vc or 0)
            except Exception as e:
                logger.info("GetMessagesViews unavailable for %s: %s", ident, e)

        items: list[dict[str, Any]] = []
        for m in msgs:
            if not m or not m.id:
                continue
            items.append(
                {
                    "message_id": int(m.id),
                    "date": m.date.isoformat() if m.date else None,
                    "views": views_map.get(int(m.id), getattr(m, "views", None)),
                    "forwards": getattr(m, "forwards", None),
                    "text_preview": (m.message or "")[:200] or None,
                }
            )
        return {
            "ok": True,
            "channel": ident,
            "items": items,
            "note": "Views require channel stats; private groups may return partial data.",
        }
    except Exception as e:
        logger.warning("fetch_channel_post_stats %s: %s", ident, e)
        return {"ok": False, "error": str(e)}
    finally:
        await client.disconnect()


def fetch_channel_post_stats_sync(channel_identifier: str, *, limit: int = 20) -> dict[str, Any]:
    return asyncio.run(fetch_channel_post_stats(channel_identifier, limit=limit))
