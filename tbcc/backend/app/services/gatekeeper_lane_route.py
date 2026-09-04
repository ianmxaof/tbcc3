"""Route approved quarantine media from hub inbox → lane Storage Hub topics.

The Storage Hub is a content-protected (noforwards) chat, so ForwardMessages is refused
for its own messages even when source and destination are the same supergroup. Media is
downloaded once and re-uploaded into each selected lane topic instead.
"""

from __future__ import annotations

import logging
from typing import Any

from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT, storage_map_by_key
from app.services.gatekeeper_review import resolve_preview_copy_target
from app.utils.telegram_peer import resolve_telethon_entity

logger = logging.getLogger(__name__)


async def route_media_to_lane_topics(storage, media: Any, lane_keys: list[str]) -> dict[str, Any]:
    """
    Copy one hub message into each selected lane subtopic (same supergroup).

    Requires telegram_message_id on the Media row. The source message is fetched and
    downloaded once, then re-uploaded per lane — the Hub is protected, so forwarding it
    raises ChatForwardsRestrictedError and delivers nothing.
    """
    msg_id = int(getattr(media, "telegram_message_id", 0) or 0)
    if msg_id <= 0:
        return {"ok": False, "reason": "no_telegram_message_id"}

    lanes = sorted({(k or "").strip().lower() for k in lane_keys if (k or "").strip()})
    if not lanes:
        return {"ok": False, "reason": "no_lanes"}

    from app.services.telegram_storage import _channel_message_media_kind

    hub_entity = await resolve_telethon_entity(storage.client, STORAGE_HUB_IDENT)

    source_msg = await storage.client.get_messages(hub_entity, ids=msg_id)
    if not source_msg or not getattr(source_msg, "media", None):
        return {"ok": False, "reason": "no_media", "source_message_id": msg_id}

    kind = _channel_message_media_kind(source_msg) or "photo"
    # One download for every lane — the bytes are re-prepared per send because
    # _prepare_file_for_send hands back a BytesIO that the send consumes.
    data = await storage.client.download_media(source_msg, bytes)
    if not data:
        return {"ok": False, "reason": "download_empty", "source_message_id": msg_id}

    existing_caption = (getattr(source_msg, "message", None) or "").strip()

    routed: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for lane in lanes:
        row = storage_map_by_key().get(lane)
        if not row:
            errors.append({"lane": lane, "error": "unknown_lane"})
            continue
        dest_thread = int(row.message_thread_id)
        try:
            from app.services.tbcc_caption_stamp import hub_intake_caption

            # skip_watermark: the media is already inside the Hub and was stamped at
            # intake. Re-watermarking on a hub→hub copy would double-mark it. Same
            # reasoning as TelegramStorage._upload_mirror_media.
            f, kwargs, _bucket = storage._prepare_file_for_send(
                data,
                kind,
                skip_watermark=True,
                source_message=source_msg,
            )
            caption = hub_intake_caption(lane, existing_caption)
            await storage.client.send_file(
                hub_entity,
                f,
                reply_to=dest_thread,
                caption=caption or None,
                **kwargs,
            )
            routed.append(
                {
                    "lane": lane,
                    "thread_id": dest_thread,
                    "topic_title": row.topic_title,
                }
            )
            try:
                from app.services.aof_library_forum_mirror import mirror_hub_message_to_library_topic

                lib_out = await mirror_hub_message_to_library_topic(
                    storage,
                    source_message_id=msg_id,
                    lane_key=lane,
                )
                if lib_out.get("ok") and not lib_out.get("skipped"):
                    routed[-1]["library_mirror"] = lib_out
            except Exception as lib_err:
                logger.warning(
                    "library forum mirror failed media_id=%s lane=%s: %s",
                    getattr(media, "id", "?"),
                    lane,
                    lib_err,
                )
                errors.append({"lane": lane, "error": f"library_mirror:{lib_err}"[:200]})
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
