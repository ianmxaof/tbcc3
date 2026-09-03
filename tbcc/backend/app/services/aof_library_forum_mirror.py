"""Mirror approved Storage Hub media → Archive of Filth library forum subtopics."""

from __future__ import annotations

import logging
import os
from typing import Any

from app.data.aof_library_forum import aof_library_forum_ident
from app.data.aof_library_forum_topic_map import library_forum_topic_for_network_key
from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT, network_key_for_storage_topic
from app.services.telegram_storage import TelegramStorage, _channel_message_media_kind
from app.utils.telegram_peer import resolve_telethon_entity

logger = logging.getLogger(__name__)

REDIS_LIBRARY_MIRROR_PREFIX = "tbcc:library_mirror:src"


def library_forum_mirror_enabled() -> bool:
    return (os.getenv("TBCC_LIBRARY_FORUM_MIRROR_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _library_mirror_redis_key(lane_key: str, source_message_id: int) -> str:
    return f"{REDIS_LIBRARY_MIRROR_PREFIX}:{lane_key}:{int(source_message_id)}"


def is_library_message_already_mirrored(lane_key: str, source_message_id: int) -> bool:
    try:
        r = _redis()
        return bool(r.get(_library_mirror_redis_key(lane_key, source_message_id)))
    except Exception:
        return False


def mark_library_message_mirrored(lane_key: str, source_message_id: int) -> None:
    try:
        r = _redis()
        r.set(_library_mirror_redis_key(lane_key, source_message_id), "1", ex=86400 * 90)
    except Exception as e:
        logger.debug("library mirror redis mark: %s", e)


def library_thread_for_storage_thread(storage_thread_id: int) -> int | None:
    key = network_key_for_storage_topic(int(storage_thread_id))
    if not key:
        return None
    row = library_forum_topic_for_network_key(key)
    return int(row.message_thread_id) if row else None


async def mirror_hub_message_to_library_topic(
    storage: TelegramStorage,
    *,
    source_message_id: int,
    lane_key: str,
) -> dict[str, Any]:
    """Re-upload one Storage Hub message into the matching library forum subtopic."""
    lane = (lane_key or "").strip().lower()
    msg_id = int(source_message_id or 0)
    if not lane or msg_id <= 0:
        return {"ok": False, "reason": "bad_args"}

    if not library_forum_mirror_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled", "lane": lane}

    row = library_forum_topic_for_network_key(lane)
    if not row:
        return {"ok": True, "skipped": True, "reason": "no_library_topic", "lane": lane}

    if is_library_message_already_mirrored(lane, msg_id):
        return {"ok": True, "skipped": True, "reason": "already_mirrored", "lane": lane}

    hub = await resolve_telethon_entity(storage.client, STORAGE_HUB_IDENT)
    library = await resolve_telethon_entity(storage.client, aof_library_forum_ident())
    msg = await storage.client.get_messages(hub, ids=msg_id)
    if not msg or not getattr(msg, "media", None):
        return {"ok": False, "reason": "no_media", "lane": lane, "message_id": msg_id}

    kind = _channel_message_media_kind(msg) or "photo"
    data = await storage.client.download_media(msg, bytes)
    if not data:
        return {"ok": False, "reason": "download_empty", "lane": lane, "message_id": msg_id}

    f, kwargs, _bucket = storage._prepare_file_for_send(data, kind, source_message=msg)
    await storage.client.send_file(
        library,
        f,
        reply_to=int(row.message_thread_id),
        silent=True,
        **kwargs,
    )
    mark_library_message_mirrored(lane, msg_id)
    return {
        "ok": True,
        "lane": lane,
        "library_thread_id": int(row.message_thread_id),
        "topic_title": row.topic_title,
        "message_id": msg_id,
    }


async def mirror_storage_topic_to_library_async(
    storage: TelegramStorage,
    storage_thread_id: int,
    *,
    limit: int = 8,
    media_types: str = "both",
) -> dict[str, Any]:
    """Bulk mirror recent media from a Storage Hub lane → library forum subtopic."""
    if not library_forum_mirror_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    library_thread_id = library_thread_for_storage_thread(int(storage_thread_id))
    if not library_thread_id:
        return {"ok": True, "skipped": True, "reason": "no_library_topic"}

    key = network_key_for_storage_topic(int(storage_thread_id)) or ""

    def _already(lane_thread: int, message_id: int) -> bool:
        return is_library_message_already_mirrored(key, message_id)

    def _mark(lane_thread: int, message_id: int) -> None:
        mark_library_message_mirrored(key, message_id)

    stats = await storage.forward_storage_topic_to_main_topic(
        STORAGE_HUB_IDENT,
        int(storage_thread_id),
        aof_library_forum_ident(),
        int(library_thread_id),
        limit=int(limit),
        media_types=media_types,
        is_already_mirrored=_already,
        on_mirrored=_mark,
    )
    return {"ok": True, "library_thread_id": library_thread_id, **stats}


def mirror_storage_topic_to_library_sync(
    storage_thread_id: int,
    *,
    limit: int = 8,
    media_types: str = "both",
    use_worker_loop: bool = False,
) -> dict[str, Any]:
    import asyncio

    from app.services.import_job_runner import _run_on_worker_loop
    from app.services.telegram_admin import run_telegram_io

    async def go(storage):
        return await mirror_storage_topic_to_library_async(
            storage,
            int(storage_thread_id),
            limit=limit,
            media_types=media_types,
        )

    coro = run_telegram_io(go)
    if use_worker_loop:
        return _run_on_worker_loop(coro)
    return asyncio.run(coro)


def enqueue_library_mirror_for_media(media_id: int) -> dict[str, Any]:
    """Queue Celery job: mirror one approved/indexed media row → library forum."""
    mid = int(media_id or 0)
    if mid <= 0:
        return {"ok": False, "reason": "bad_media_id"}
    if not library_forum_mirror_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled", "media_id": mid}
    try:
        from app.workers.gatekeeper_review_worker import library_mirror_media_task

        library_mirror_media_task.delay(mid)
        return {"ok": True, "queued": True, "media_id": mid}
    except Exception as e:
        logger.warning("library mirror enqueue failed media_id=%s: %s", mid, e, exc_info=True)
        return {"ok": False, "reason": str(e)[:200], "media_id": mid}
