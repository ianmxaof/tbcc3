"""Move deposited Storage Hub media into SENT VAULT — permanent master archive; emoji-keyed albums only."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_storage_hub_map import (
    STORAGE_HUB_IDENT,
    category_emoji_for_network_key,
)
from app.models.media import Media

logger = logging.getLogger(__name__)

SENT_CACHE_STAMP = "✅"
BUF_PREFIX = "tbcc:sent_cache:buf"
BUF_TTL_SECONDS = 86400 * 7
MIN_ALBUM_POST = 2


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def storage_sent_cache_enabled() -> bool:
    return (os.getenv("TBCC_STORAGE_SENT_CACHE_ENABLED") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def storage_deposit_lane_evict_enabled() -> bool:
    """Remove deposited (and duplicate-skipped) media from Storage Hub lanes after /deposit."""
    return (os.getenv("TBCC_STORAGE_DEPOSIT_LANE_EVICT") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def storage_sent_cache_topic_id() -> int:
    raw = (os.getenv("TBCC_STORAGE_SENT_CACHE_TOPIC_ID") or "12345").strip()
    return int(raw)


def sent_cache_album_size() -> int:
    raw = (os.getenv("TBCC_SENT_CACHE_ALBUM_SIZE") or "5").strip()
    try:
        return max(MIN_ALBUM_POST, min(10, int(raw)))
    except ValueError:
        return 5


def sent_cache_caption(network_key: str | None) -> str:
    from app.services.tbcc_caption_stamp import append_tbcc_tags, tbcc_lane_tag

    stamp = f"{SENT_CACHE_STAMP}{category_emoji_for_network_key(network_key)}"
    tag = tbcc_lane_tag(network_key)
    return append_tbcc_tags(stamp, tag) if tag else stamp


def _buf_key(network_key: str) -> str:
    return f"{BUF_PREFIX}:{(network_key or '').strip().lower()}"


def _media_bucket(media_type: str | None) -> str:
    t = (media_type or "photo").strip().lower()
    return "video" if t == "video" else "photo"


def _dedupe_buffer_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep first row per media_id (retries must not double-post the same clip)."""
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for row in items:
        try:
            mid = int(row.get("media_id") or 0)
        except (TypeError, ValueError):
            continue
        if mid <= 0 or mid in seen:
            continue
        seen.add(mid)
        out.append(row)
    return out


def _load_buffer(network_key: str) -> list[dict[str, Any]]:
    nk = (network_key or "").strip().lower()
    if not nk:
        return []
    try:
        raw_items = _redis().lrange(_buf_key(nk), 0, -1) or []
    except Exception:
        logger.debug("sent cache buffer read failed nk=%s", nk, exc_info=True)
        return []
    out: list[dict[str, Any]] = []
    for raw in raw_items:
        try:
            row = json.loads(raw)
            if isinstance(row, dict) and row.get("message_id") and row.get("media_id"):
                out.append(row)
        except (TypeError, json.JSONDecodeError):
            continue
    return _dedupe_buffer_items(out)


def _save_buffer(network_key: str, items: list[dict[str, Any]]) -> None:
    nk = (network_key or "").strip().lower()
    if not nk:
        return
    try:
        pipe = _redis().pipeline()
        key = _buf_key(nk)
        pipe.delete(key)
        for row in _dedupe_buffer_items(items):
            pipe.rpush(key, json.dumps(row))
        pipe.expire(key, BUF_TTL_SECONDS)
        pipe.execute()
    except Exception:
        logger.debug("sent cache buffer write failed nk=%s", nk, exc_info=True)


def pending_sent_cache_count(network_key: str) -> int:
    return len(_load_buffer(network_key))


def _coerce_message(messages):
    if messages is None:
        return None
    if isinstance(messages, list):
        return messages[0] if messages else None
    return messages


def _partition_by_bucket(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {"photo": [], "video": []}
    for row in items:
        buckets[_media_bucket(str(row.get("media_type") or "photo"))].append(row)
    return buckets


def _take_album_chunks(
    items: list[dict[str, Any]],
    *,
    album_size: int,
    force: bool,
) -> tuple[list[list[dict[str, Any]]], list[dict[str, Any]]]:
    """Split into full albums; keep remainder unless force and ≥ MIN_ALBUM_POST."""
    albums: list[list[dict[str, Any]]] = []
    remaining = list(items)
    while len(remaining) >= album_size:
        albums.append(remaining[:album_size])
        remaining = remaining[album_size:]
    if force and len(remaining) >= MIN_ALBUM_POST:
        albums.append(remaining)
        remaining = []
    return albums, remaining


async def _post_cache_album(
    client,
    entity,
    cache_tid: int,
    chunk: list[dict[str, Any]],
    *,
    caption: str,
    hub_ident: str,
) -> dict[str, Any]:
    """Post one homogeneous album chunk into SENT CACHE; delete source hub messages."""
    from app.utils.telegram_peer import resolve_telethon_entity

    hub_entity = entity
    if str(getattr(entity, "id", "")) != STORAGE_HUB_IDENT.lstrip("-"):
        hub_entity = await resolve_telethon_entity(client, hub_ident)

    medias = []
    source_msgs = []
    row_meta: list[dict[str, Any]] = []
    seen_media: set[int] = set()
    for row in _dedupe_buffer_items(chunk):
        try:
            old_mid = int(row.get("message_id") or 0)
            media_id = int(row.get("media_id") or 0)
        except (TypeError, ValueError):
            continue
        if old_mid <= 0 or media_id <= 0 or media_id in seen_media:
            continue
        seen_media.add(media_id)
        messages = await client.get_messages(hub_entity, ids=old_mid)
        msg = _coerce_message(messages)
        if not msg or not getattr(msg, "media", None):
            continue
        medias.append(msg.media)
        source_msgs.append(msg)
        row_meta.append({"media_id": media_id, "message_id": old_mid})

    if len(medias) < MIN_ALBUM_POST:
        return {"ok": False, "reason": "insufficient_media", "count": len(medias)}

    try:
        sent = await client.send_file(
            hub_entity,
            medias,
            caption=caption,
            reply_to=cache_tid,
            silent=True,
        )
    except Exception as e:
        logger.warning("sent cache album post failed: %s", e, exc_info=True)
        return {"ok": False, "error": str(e)[:200], "count": len(medias)}

    sent_list = sent if isinstance(sent, list) else [sent]
    new_mid = int(getattr(sent_list[0], "id", 0) or 0)
    if new_mid <= 0:
        return {"ok": False, "reason": "no_message_id", "count": len(medias)}

    old_ids = [int(m.id) for m in source_msgs if getattr(m, "id", None)]
    try:
        if old_ids:
            await client.delete_messages(hub_entity, old_ids)
    except Exception:
        logger.debug("sent cache source cleanup failed", exc_info=True)

    moved_items: list[dict[str, Any]] = []
    for i, r in enumerate(row_meta):
        cache_mid = new_mid
        if i < len(sent_list):
            cache_mid = int(getattr(sent_list[i], "id", 0) or 0) or new_mid
        moved_items.append(
            {"media_id": int(r["media_id"]), "cache_message_id": cache_mid}
        )
    return {
        "ok": True,
        "count": len(medias),
        "cache_message_id": new_mid,
        "moved_items": moved_items,
        "source_message_ids": old_ids,
    }


async def flush_sent_cache_buffer(
    storage,
    db: Session,
    network_key: str,
    *,
    hub_ident: str = STORAGE_HUB_IDENT,
    force: bool = False,
) -> dict[str, Any]:
    """Flush pending staging buffer for one emoji lane into SENT VAULT albums (does not delete vault media)."""
    if not storage_sent_cache_enabled():
        return {"skipped": 1, "albums_posted": 0}
    nk = (network_key or "").strip().lower()
    if not nk:
        return {"ok": False, "reason": "no_network_key"}

    pending = _load_buffer(nk)
    if not pending:
        return {"ok": True, "albums_posted": 0, "pending": 0}

    from app.utils.telegram_peer import resolve_telethon_entity

    client = storage.client
    entity = await resolve_telethon_entity(client, hub_ident)
    cache_tid = storage_sent_cache_topic_id()
    caption = sent_cache_caption(nk)
    album_size = sent_cache_album_size()

    remainder: list[dict[str, Any]] = []
    albums_posted = 0
    errors = 0
    moved_total = 0
    moved_items: list[dict[str, Any]] = []

    for bucket_name, bucket_items in _partition_by_bucket(pending).items():
        if not bucket_items:
            continue
        chunks, left = _take_album_chunks(bucket_items, album_size=album_size, force=force)
        remainder.extend(left)
        for chunk in chunks:
            out = await _post_cache_album(
                client,
                entity,
                cache_tid,
                chunk,
                caption=caption,
                hub_ident=hub_ident,
            )
            if not out.get("ok"):
                errors += 1
                remainder.extend(chunk)
                continue
            albums_posted += 1
            moved_total += int(out.get("count") or 0)
            for item in out.get("moved_items") or []:
                mid = int(item.get("media_id") or 0)
                cache_mid = int(item.get("cache_message_id") or 0)
                if mid > 0 and cache_mid > 0:
                    rec = db.query(Media).filter(Media.id == mid).first()
                    if rec:
                        rec.telegram_message_id = cache_mid
                    moved_items.append(item)
            await asyncio.sleep(0.15)

    if moved_items:
        db.commit()

    _save_buffer(nk, remainder)
    return {
        "ok": errors == 0,
        "network_key": nk,
        "caption": caption,
        "albums_posted": albums_posted,
        "moved": moved_total,
        "errors": errors,
        "pending_left": len(remainder),
        "moved_items": moved_items,
        "cache_topic_id": cache_tid,
    }


async def flush_all_sent_cache_emoji_buffers(
    storage,
    db: Session,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Flush every emoji lane's pending staging buffer into SENT VAULT albums (safe — no vault purge)."""
    from app.data.aof_storage_hub_map import AOF_STORAGE_TOPIC_MAP

    lanes = sorted(
        {(m.network_key or "").strip().lower() for m in AOF_STORAGE_TOPIC_MAP if m.network_key}
    )
    out: dict[str, Any] = {"lanes": [], "albums_posted": 0}
    for nk in lanes:
        if pending_sent_cache_count(nk) < MIN_ALBUM_POST and not force:
            continue
        report = await flush_sent_cache_buffer(storage, db, nk, force=force)
        if int(report.get("albums_posted") or 0) > 0 or int(report.get("pending_left") or 0) > 0:
            out["lanes"].append(report)
            out["albums_posted"] += int(report.get("albums_posted") or 0)
    return out


async def evict_lane_messages(
    storage,
    hub_ident: str,
    message_ids: list[int],
) -> dict[str, Any]:
    """Delete lane messages already represented in the pool (duplicate deposit hygiene)."""
    ids = sorted({int(x) for x in message_ids if int(x) > 0})
    if not ids:
        return {"evicted": 0, "errors": 0}
    from app.utils.telegram_peer import resolve_telethon_entity

    client = storage.client
    entity = await resolve_telethon_entity(client, hub_ident)
    errors = 0
    evicted = 0
    chunk = 80
    for i in range(0, len(ids), chunk):
        batch = ids[i : i + chunk]
        try:
            await client.delete_messages(entity, batch)
            evicted += len(batch)
        except Exception:
            errors += 1
            logger.warning("lane evict failed hub=%s ids=%s", hub_ident, batch[:5], exc_info=True)
        await asyncio.sleep(0.1)
    return {"evicted": evicted, "errors": errors, "message_ids": ids}


async def move_deposit_batch_to_sent_cache(
    storage,
    db: Session,
    *,
    stored_messages: list[dict],
    network_key: str | None,
    hub_ident: str = STORAGE_HUB_IDENT,
    force_flush: bool = False,
) -> dict[str, int | list | str | bool]:
    """
    Buffer deposited items per emoji lane, then post SENT VAULT albums (never singles).
    Leftovers stay in staging buffer until the next deposit fills an album.
    Vault media is permanent — nothing here deletes archived vault posts.
    """
    if not storage_sent_cache_enabled():
        return {"skipped": 1, "moved": 0, "errors": 0}
    if not stored_messages:
        return {"moved": 0, "errors": 0}

    nk = (network_key or "").strip().lower()
    if not nk:
        return {"moved": 0, "errors": len(stored_messages), "reason": "no_network_key"}

    pending = _load_buffer(nk)
    pending_ids = {
        int(r.get("media_id") or 0)
        for r in pending
        if int(r.get("media_id") or 0) > 0
    }
    errors = 0
    skipped_dup = 0
    for row in stored_messages:
        if not isinstance(row, dict):
            errors += 1
            continue
        try:
            old_mid = int(row.get("message_id") or 0)
            media_id = int(row.get("media_id") or 0)
        except (TypeError, ValueError):
            errors += 1
            continue
        if old_mid <= 0 or media_id <= 0:
            errors += 1
            continue
        if media_id in pending_ids:
            # Idempotent: Telethon import-io retries re-enter this path after Redis
            # append already landed — do not stage the same clip twice.
            skipped_dup += 1
            continue
        rec = db.query(Media).filter(Media.id == media_id).first()
        media_type = (rec.media_type if rec else None) or row.get("media_type") or "photo"
        pending.append(
            {
                "media_id": media_id,
                "message_id": old_mid,
                "media_type": _media_bucket(str(media_type)),
                "ts": time.time(),
            }
        )
        pending_ids.add(media_id)

    _save_buffer(nk, pending)
    flush_out = await flush_sent_cache_buffer(
        storage,
        db,
        nk,
        hub_ident=hub_ident,
        force=force_flush,
    )

    return {
        "moved": int(flush_out.get("moved") or 0),
        "errors": errors + int(flush_out.get("errors") or 0),
        "skipped_dup": skipped_dup,
        "cache_topic_id": flush_out.get("cache_topic_id"),
        "caption": flush_out.get("caption"),
        "albums_posted": int(flush_out.get("albums_posted") or 0),
        "pending_left": int(flush_out.get("pending_left") or 0),
        "moved_items": list(flush_out.get("moved_items") or []),
        "network_key": nk,
    }
