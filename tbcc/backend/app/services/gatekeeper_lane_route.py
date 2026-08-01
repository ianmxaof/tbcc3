"""Forward approved quarantine media from hub inbox → lane Storage Hub topics."""

from __future__ import annotations

import logging
from typing import Any

from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT, storage_map_by_key
from app.services.gatekeeper_review import resolve_preview_copy_target
from app.utils.telegram_peer import resolve_telethon_entity

logger = logging.getLogger(__name__)


async def route_media_to_lane_topics(storage, media: Any, lane_keys: list[str]) -> dict[str, Any]:
    """
    Forward one hub message into each selected lane subtopic (same supergroup).
    Requires telegram_message_id on the Media row.
    """
    msg_id = int(getattr(media, "telegram_message_id", 0) or 0)
    if msg_id <= 0:
        return {"ok": False, "reason": "no_telegram_message_id"}

    lanes = sorted({(k or "").strip().lower() for k in lane_keys if (k or "").strip()})
    if not lanes:
        return {"ok": False, "reason": "no_lanes"}

    hub_entity = await resolve_telethon_entity(storage.client, STORAGE_HUB_IDENT)
    routed: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for lane in lanes:
        row = storage_map_by_key().get(lane)
        if not row:
            errors.append({"lane": lane, "error": "unknown_lane"})
            continue
        dest_thread = int(row.message_thread_id)
        try:
            await storage.client.forward_messages(
                hub_entity,
                msg_id,
                from_peer=hub_entity,
                reply_to=dest_thread,
            )
            routed.append(
                {
                    "lane": lane,
                    "thread_id": dest_thread,
                    "topic_title": row.topic_title,
                }
            )
        except Exception as e:
            logger.warning(
                "gatekeeper route failed media_id=%s lane=%s: %s",
                getattr(media, "id", "?"),
                lane,
                e,
            )
            errors.append({"lane": lane, "error": str(e)[:200]})

    return {
        "ok": bool(routed),
        "routed": routed,
        "errors": errors,
        "source_message_id": msg_id,
        "preview": resolve_preview_copy_target(media),
    }
