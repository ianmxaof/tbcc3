"""Rebundle loose singles in a Telegram chat/topic into albums (Storage Hub or any peer)."""

from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from typing import Any

from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT
from app.services.telegram_storage import (
    TELEGRAM_ALBUM_MAX,
    _channel_message_media_kind,
    _message_mirror_bucket,
    batch_messages_for_album_mirror,
)

logger = logging.getLogger(__name__)

DEFAULT_ALBUM_SIZE = 10
DEFAULT_MAX_SCAN = 2000


def topic_rebundle_album_size() -> int:
    raw = (os.getenv("TBCC_TOPIC_REBUNDLE_ALBUM_SIZE") or str(DEFAULT_ALBUM_SIZE)).strip()
    try:
        return max(2, min(TELEGRAM_ALBUM_MAX, int(raw)))
    except ValueError:
        return DEFAULT_ALBUM_SIZE


def topic_rebundle_max_scan() -> int:
    raw = (os.getenv("TBCC_TOPIC_REBUNDLE_MAX_SCAN") or str(DEFAULT_MAX_SCAN)).strip()
    try:
        return max(50, min(5000, int(raw)))
    except ValueError:
        return DEFAULT_MAX_SCAN


def topic_rebundle_delete_sources() -> bool:
    """Delete source loose messages after a successful album post (default on)."""
    raw = (os.getenv("TBCC_TOPIC_REBUNDLE_DELETE_SOURCES") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def classify_loose_media_messages(messages: list) -> tuple[list, list]:
    """
    Split topic media into loose singles vs existing multi-message albums.
    Returns (loose_messages, existing_album_messages).
    """
    loose: list = []
    by_group: dict[int, list] = {}
    for msg in messages or []:
        if not _channel_message_media_kind(msg):
            continue
        gid = getattr(msg, "grouped_id", None)
        if not gid:
            loose.append(msg)
            continue
        by_group.setdefault(int(gid), []).append(msg)

    existing_album: list = []
    for group in by_group.values():
        if len(group) >= 2:
            existing_album.extend(group)
        else:
            loose.extend(group)
    return loose, existing_album


def plan_topic_rebundle_batches(
    loose_messages: list,
    *,
    album_size: int | None = None,
    allow_partial: bool = True,
) -> dict[str, Any]:
    """
    Plan album batches from loose singles (photos/videos separately).

    When allow_partial is True (default), leftover singles after full albums become
    one final partial album per media type (min 1 item).
    """
    size = album_size or topic_rebundle_album_size()
    by_bucket: dict[str, list] = defaultdict(list)
    for msg in loose_messages:
        by_bucket[_message_mirror_bucket(msg)].append(msg)

    batches: list[list] = []
    for bucket in ("photo", "video"):
        rows = by_bucket.get(bucket) or []
        if not rows:
            continue
        batches.extend(
            batch_messages_for_album_mirror(
                rows,
                max_size=size,
                # Chunk into full albums + final partial (library always emits partials
                # when require_full_albums=True; we filter them off when allow_partial=False).
                require_full_albums=True,
            )
        )

    if not allow_partial:
        batches = [b for b in batches if len(b) >= size]

    full_albums = sum(1 for b in batches if len(b) >= size)
    partial_albums = sum(1 for b in batches if 0 < len(b) < size)
    items_in_albums = sum(len(b) for b in batches)
    leftover = max(0, len(loose_messages) - items_in_albums)
    return {
        "album_size": size,
        "allow_partial": bool(allow_partial),
        "loose_count": len(loose_messages),
        "full_albums": full_albums,
        "partial_albums": partial_albums,
        "album_batches": len(batches),
        "items_in_albums": items_in_albums,
        "leftover_singles": leftover,
        "batches": batches,
    }


def _iter_kwargs(message_thread_id: int | None) -> dict[str, Any]:
    if message_thread_id is None:
        return {}
    return {"reply_to": int(message_thread_id)}


def _send_kwargs(message_thread_id: int | None) -> dict[str, Any]:
    kw: dict[str, Any] = {"silent": True}
    if message_thread_id is not None:
        kw["reply_to"] = int(message_thread_id)
    return kw


async def scan_storage_topic_loose_media(
    storage,
    *,
    message_thread_id: int | None,
    channel_ident: str = STORAGE_HUB_IDENT,
    max_scan: int | None = None,
    allow_partial: bool = True,
) -> dict[str, Any]:
    from app.utils.telegram_peer import resolve_telethon_entity

    tid = int(message_thread_id) if message_thread_id is not None else None
    limit = max_scan or topic_rebundle_max_scan()
    entity = await resolve_telethon_entity(storage.client, str(channel_ident))
    media_msgs: list = []
    scanned = 0
    async for message in storage.client.iter_messages(
        entity, limit=limit, **_iter_kwargs(tid)
    ):
        scanned += 1
        if _channel_message_media_kind(message):
            media_msgs.append(message)

    media_msgs.reverse()
    loose, existing = classify_loose_media_messages(media_msgs)
    plan = plan_topic_rebundle_batches(loose, allow_partial=allow_partial)
    return {
        "ok": True,
        "dry_run": True,
        "channel_ident": str(channel_ident),
        "message_thread_id": tid,
        "messages_scanned": scanned,
        "media_messages": len(media_msgs),
        "existing_album_messages": len(existing),
        "loose_count": plan["loose_count"],
        "full_albums": plan["full_albums"],
        "partial_albums": plan["partial_albums"],
        "leftover_singles": plan["leftover_singles"],
        "album_size": plan["album_size"],
        "allow_partial": plan["allow_partial"],
        "items_in_albums": plan["items_in_albums"],
        "album_batches": plan["album_batches"],
    }


async def rebundle_storage_topic_loose_media_async(
    storage,
    *,
    message_thread_id: int | None,
    channel_ident: str = STORAGE_HUB_IDENT,
    album_size: int | None = None,
    max_scan: int | None = None,
    dry_run: bool = False,
    allow_partial: bool = True,
    delete_sources: bool | None = None,
) -> dict[str, Any]:
    from app.utils.telegram_peer import resolve_telethon_entity

    do_delete = topic_rebundle_delete_sources() if delete_sources is None else bool(delete_sources)

    scan = await scan_storage_topic_loose_media(
        storage,
        message_thread_id=message_thread_id,
        channel_ident=channel_ident,
        max_scan=max_scan,
        allow_partial=allow_partial,
    )
    if dry_run:
        return {**scan, "delete_sources": do_delete}

    tid = int(message_thread_id) if message_thread_id is not None else None
    size = album_size or topic_rebundle_album_size()
    limit = max_scan or topic_rebundle_max_scan()
    entity = await resolve_telethon_entity(storage.client, str(channel_ident))

    media_msgs: list = []
    async for message in storage.client.iter_messages(
        entity, limit=limit, **_iter_kwargs(tid)
    ):
        if _channel_message_media_kind(message):
            media_msgs.append(message)
    media_msgs.reverse()
    loose, _existing = classify_loose_media_messages(media_msgs)
    plan = plan_topic_rebundle_batches(loose, album_size=size, allow_partial=allow_partial)
    batches: list[list] = plan.get("batches") or []

    albums_posted = 0
    partial_posted = 0
    errors = 0
    sources_deleted = 0
    delete_errors = 0
    for batch in batches:
        if not batch:
            continue
        try:
            await storage._send_album_chunk_refs(
                batch,
                destination=entity,
                send_kwargs=_send_kwargs(tid),
            )
            albums_posted += 1
            if len(batch) < size:
                partial_posted += 1
            if do_delete:
                ids = [int(getattr(m, "id", 0) or 0) for m in batch]
                ids = [i for i in ids if i > 0]
                if ids:
                    try:
                        await storage.client.delete_messages(entity, ids)
                        sources_deleted += len(ids)
                    except Exception as de:
                        delete_errors += 1
                        logger.warning(
                            "topic rebundle delete sources failed peer=%s thread=%s n=%s: %s",
                            channel_ident,
                            tid,
                            len(ids),
                            de,
                            exc_info=True,
                        )
            await asyncio.sleep(0.5)
        except Exception as e:
            errors += 1
            logger.warning(
                "topic rebundle album post failed peer=%s thread=%s size=%s: %s",
                channel_ident,
                tid,
                len(batch),
                e,
                exc_info=True,
            )

    return {
        **scan,
        "dry_run": False,
        "albums_posted": albums_posted,
        "partial_posted": partial_posted,
        "errors": errors,
        "delete_sources": do_delete,
        "sources_deleted": sources_deleted,
        "delete_errors": delete_errors,
    }


def rebundle_storage_topic_loose_media_sync(
    *,
    message_thread_id: int | None,
    channel_ident: str = STORAGE_HUB_IDENT,
    album_size: int | None = None,
    max_scan: int | None = None,
    dry_run: bool = False,
    allow_partial: bool = True,
    delete_sources: bool | None = None,
) -> dict[str, Any]:
    from app.services.import_job_runner import _run_on_worker_loop
    from app.services.telegram_admin import run_telegram_import_io
    from app.services.telegram_storage import TelegramStorage

    async def _go(storage: TelegramStorage):
        return await rebundle_storage_topic_loose_media_async(
            storage,
            message_thread_id=message_thread_id,
            channel_ident=channel_ident,
            album_size=album_size,
            max_scan=max_scan,
            dry_run=dry_run,
            allow_partial=allow_partial,
            delete_sources=delete_sources,
        )

    return _run_on_worker_loop(run_telegram_import_io(_go))


def format_topic_rebundle_summary(report: dict[str, Any], *, html: bool = True) -> str:
    loose = int(report.get("loose_count") or 0)
    full = int(report.get("full_albums") or 0)
    partial = int(report.get("partial_albums") or 0)
    left = int(report.get("leftover_singles") or 0)
    size = int(report.get("album_size") or topic_rebundle_album_size())
    posted = int(report.get("albums_posted") or 0)
    partial_posted = int(report.get("partial_posted") or 0)
    allow_partial = report.get("allow_partial", True)
    do_delete = report.get("delete_sources", topic_rebundle_delete_sources())
    deleted = int(report.get("sources_deleted") or 0)

    if report.get("dry_run") and not report.get("albums_posted"):
        if loose == 0:
            body = "No loose media found."
        elif full == 0 and partial == 0:
            body = f"{loose} loose item(s) — nothing to album."
        else:
            parts = [f"{loose} loose → {full}×{size}"]
            if allow_partial and partial:
                parts.append(f"+ {partial} partial")
            elif left:
                parts.append(f"(+ {left} leftover)")
            if do_delete:
                parts.append("(sources will be deleted)")
            body = " ".join(parts)
        return f"<b>🔗 Rebundle preview</b>\n{body}" if html else f"Rebundle preview: {body}"

    if posted:
        extra = f" ({partial_posted} partial)" if partial_posted else ""
        if do_delete:
            src = f"deleted {deleted} source msg(s)" if deleted else "source delete attempted"
        else:
            src = "sources kept"
        body = f"Posted {posted} album(s){extra} (full size {size}; {src})."
        return f"<b>🔗 Rebundle done</b>\n{body}" if html else f"Rebundle done: {body}"
    err = report.get("error") or "nothing posted"
    return f"<b>🔗 Rebundle</b>\n{err}" if html else f"Rebundle: {err}"
