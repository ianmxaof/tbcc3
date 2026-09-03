"""Recycle dry lane pools from SENT VAULT (emoji-stamped archive) — lightweight cadence recovery."""

from __future__ import annotations

import asyncio
import logging
import os
import random
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto, MessageMediaWebPage

from app.data.aof_network import AOF_NETWORK_CHANNELS
from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT, category_emoji_for_network_key
from app.models.content_pool import ContentPool
from app.models.media import Media
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.storage_sent_cache import (
    SENT_CACHE_STAMP,
    sent_cache_caption,
    storage_sent_cache_enabled,
    storage_sent_cache_topic_id,
)
from app.services.tbcc_caption_stamp import parse_tbcc_lane_from_caption

logger = logging.getLogger(__name__)

RECYCLE_TAG = "sent_vault_recycled"

# Loot Room, VIP-style lanes, library twin, intake — new content only (no vault recycle).
SENT_VAULT_RECYCLE_SKIP_KEYS: frozenset[str] = frozenset(
    {"main", "inbox", "packs", "full_length", "vip", "library"}
)


@dataclass
class SentVaultRefillPlan:
    key: str
    pool_id: int
    pool_name: str
    approved: int
    need: int
    vault_matches: int = 0
    restored: list[Media] = field(default_factory=list)


def sent_vault_lane_refill_enabled() -> bool:
    if not storage_sent_cache_enabled():
        return False
    raw = (os.getenv("TBCC_SENT_VAULT_LANE_REFILL_ENABLED") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def sent_vault_dry_spell_refill_enabled() -> bool:
    """On-demand vault recycle when a scheduled send finds an empty pool (default on)."""
    if not sent_vault_lane_refill_enabled():
        return False
    raw = (os.getenv("TBCC_SENT_VAULT_DRY_SPELL_REFILL") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def network_key_for_pool_name(pool_name: str | None) -> str | None:
    name = (pool_name or "").strip()
    if not name:
        return None
    for ch in AOF_NETWORK_CHANNELS:
        if ch.pool_name == name:
            return ch.key
    return None


def network_key_for_pool_id(db: Session, pool_id: int) -> str | None:
    pool = db.query(ContentPool).filter(ContentPool.id == int(pool_id)).first()
    if not pool:
        return None
    return network_key_for_pool_name(getattr(pool, "name", None))


def dry_lane_min_approved() -> int:
    raw = (os.getenv("TBCC_SENT_VAULT_REFILL_MIN_APPROVED") or "1").strip()
    try:
        return max(1, min(20, int(raw)))
    except ValueError:
        return 1


def sent_vault_refill_target() -> int:
    raw = (os.getenv("TBCC_SENT_VAULT_REFILL_TARGET") or "10").strip()
    try:
        return max(1, min(60, int(raw)))
    except ValueError:
        return 10


def sent_vault_scan_limit() -> int:
    raw = (os.getenv("TBCC_SENT_VAULT_REFILL_SCAN_LIMIT") or "400").strip()
    try:
        return max(50, min(2000, int(raw)))
    except ValueError:
        return 400


def _pool_for(db: Session, pool_name: str) -> ContentPool | None:
    return db.query(ContentPool).filter(ContentPool.name == pool_name).first()


def _vault_source_label() -> str:
    return f"{STORAGE_HUB_IDENT}#topic:{storage_sent_cache_topic_id()}"


def vault_caption_matches_lane(caption: str | None, network_key: str) -> bool:
    """True when a SENT VAULT caption belongs to ``network_key`` (tag or ✅+emoji)."""
    nk = (network_key or "").strip().lower()
    if not nk:
        return False
    text = caption or ""
    parsed = parse_tbcc_lane_from_caption(text)
    if parsed == nk:
        return True
    if SENT_CACHE_STAMP not in text:
        return False
    return category_emoji_for_network_key(nk) in text


def lane_key_from_vault_caption(caption: str | None, candidate_keys: set[str]) -> str | None:
    parsed = parse_tbcc_lane_from_caption(caption)
    if parsed and parsed in candidate_keys:
        return parsed
    text = caption or ""
    if SENT_CACHE_STAMP not in text:
        return None
    for key in candidate_keys:
        if category_emoji_for_network_key(key) in text:
            return key
    return None


def _file_ids_from_message(message) -> tuple[str, str, str] | None:
    media = getattr(message, "media", None)
    if media is None:
        return None
    if isinstance(media, MessageMediaPhoto):
        fid = str(media.photo.id)
        return fid, fid, "photo"
    if isinstance(media, MessageMediaDocument):
        fid = str(media.document.id)
        mime = (media.document.mime_type or "").lower()
        if "video" in mime:
            kind = "video"
        elif "image" in mime or mime in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            kind = "photo"
        else:
            kind = "document"
        return fid, fid, kind
    if isinstance(media, MessageMediaWebPage):
        wp = media.webpage
        if wp and getattr(wp, "photo", None):
            fid = str(wp.photo.id)
            return fid, fid, "photo"
        if wp and getattr(wp, "document", None):
            fid = str(wp.document.id)
            return fid, fid, "document"
    return None


def _tag_recycled(row: Media) -> None:
    tags = [t.strip() for t in (row.tags or "").split(",") if t.strip()]
    if RECYCLE_TAG not in tags:
        tags.append(RECYCLE_TAG)
    row.tags = ",".join(tags)


def approve_media_from_vault_message(
    db: Session,
    message,
    *,
    pool_id: int,
    network_key: str,
) -> Media | None:
    """Index one vault Telegram message into ``approved`` pool rotation (no re-download)."""
    parsed = _file_ids_from_message(message)
    if not parsed:
        return None
    file_id, file_unique_id, media_type = parsed
    mid = int(getattr(message, "id", 0) or 0)
    if mid <= 0:
        return None

    source = _vault_source_label()
    existing = (
        db.query(Media)
        .filter(Media.file_unique_id == file_unique_id, Media.pool_id == int(pool_id))
        .first()
    )
    if existing:
        if (existing.status or "").strip().lower() == "approved":
            return None
        existing.status = "approved"
        existing.telegram_message_id = mid
        existing.source_channel = source
        _tag_recycled(existing)
        return existing

    row = Media(
        telegram_message_id=mid,
        file_id=file_id,
        file_unique_id=file_unique_id,
        media_type=media_type,
        source_channel=source,
        pool_id=int(pool_id),
        status="approved",
        tags=RECYCLE_TAG,
    )
    db.add(row)
    return row


def build_sent_vault_refill_plan(
    db: Session,
    *,
    target: int | None = None,
    min_approved: int | None = None,
) -> dict[str, SentVaultRefillPlan]:
    tgt = sent_vault_refill_target() if target is None else int(target)
    floor = dry_lane_min_approved() if min_approved is None else int(min_approved)
    plan: dict[str, SentVaultRefillPlan] = {}

    for ch in AOF_NETWORK_CHANNELS:
        if ch.key in SENT_VAULT_RECYCLE_SKIP_KEYS:
            continue
        pool = _pool_for(db, ch.pool_name)
        if not pool:
            continue
        approved = (
            db.query(Media).filter(Media.pool_id == int(pool.id), Media.status == "approved").count()
        )
        need = max(0, tgt - approved) if approved < floor else 0
        plan[ch.key] = SentVaultRefillPlan(
            key=ch.key,
            pool_id=int(pool.id),
            pool_name=ch.pool_name,
            approved=int(approved),
            need=int(need),
        )
    return plan


def _sample_vault_buckets(
    buckets: dict[str, list[Any]],
    need_by_key: dict[str, int],
) -> dict[str, list[Any]]:
    """Random pick per lane from all vault matches (not newest-first sequential)."""
    out: dict[str, list[Any]] = {}
    for key, need in need_by_key.items():
        pool = list(buckets.get(key) or [])
        random.shuffle(pool)
        out[key] = pool[: max(0, int(need))]
    return out


async def _scan_vault_messages(
    storage,
    *,
    need_by_key: dict[str, int],
    scan_limit: int,
) -> dict[str, list[Any]]:
    """One pass over SENT VAULT — collect lane matches, then random-sample per lane."""
    from app.utils.telegram_peer import resolve_telethon_entity

    if not need_by_key:
        return {}

    client = storage.client
    hub = await resolve_telethon_entity(client, STORAGE_HUB_IDENT)
    cache_tid = storage_sent_cache_topic_id()
    candidates = set(need_by_key)
    buckets: dict[str, list[Any]] = {k: [] for k in need_by_key}
    scanned = 0

    async for message in client.iter_messages(hub, limit=scan_limit, reply_to=cache_tid):
        scanned += 1
        if not getattr(message, "media", None):
            continue
        cap = getattr(message, "message", None) or getattr(message, "text", None) or ""
        lane = lane_key_from_vault_caption(str(cap), candidates)
        if lane and lane in buckets:
            buckets[lane].append(message)

    sampled = _sample_vault_buckets(buckets, need_by_key)
    logger.info(
        "sent vault scan: scanned=%s lanes=%s pool_matches=%s picked=%s",
        scanned,
        list(need_by_key),
        {k: len(v) for k, v in buckets.items()},
        {k: len(v) for k, v in sampled.items()},
    )
    return sampled


async def _apply_sent_vault_refill_async(
    db: Session,
    plan: dict[str, SentVaultRefillPlan],
    *,
    unpause: bool = False,
) -> dict[str, int]:
    from app.services.telegram_admin import run_telegram_album_composer_io

    need_by_key = {k: v.need for k, v in plan.items() if v.need > 0}
    if not need_by_key:
        return {}

    restored_by_lane: dict[str, int] = {}

    async def _go(storage) -> None:
        buckets = await _scan_vault_messages(
            storage, need_by_key=need_by_key, scan_limit=sent_vault_scan_limit()
        )
        for key, entry in plan.items():
            if entry.need <= 0:
                continue
            messages = list(buckets.get(key) or [])
            entry.vault_matches = len(messages)
            restored: list[Media] = []
            for msg in messages[: entry.need]:
                row = approve_media_from_vault_message(
                    db, msg, pool_id=entry.pool_id, network_key=key
                )
                if row is not None:
                    restored.append(row)
            if restored:
                db.commit()
                restored_by_lane[key] = len(restored)
                entry.restored = restored
                if unpause:
                    scheds = (
                        db.query(ScheduledTextPost)
                        .filter(ScheduledTextPost.pool_id == entry.pool_id)
                        .filter(ScheduledTextPost.posting_auto_paused_at.isnot(None))
                        .all()
                    )
                    for s in scheds:
                        s.posting_auto_paused_at = None
                        if hasattr(s, "posting_auto_pause_reason"):
                            s.posting_auto_pause_reason = None
                    if scheds:
                        db.commit()

    await run_telegram_album_composer_io(_go)
    return restored_by_lane


def refill_dry_lanes_from_sent_vault_sync(
    db: Session,
    *,
    target: int | None = None,
    min_approved: int | None = None,
    execute: bool = False,
    unpause: bool = False,
) -> dict[str, Any]:
    plan = build_sent_vault_refill_plan(db, target=target, min_approved=min_approved)
    preview: dict[str, dict[str, Any]] = {}
    would_restore = 0
    for key, entry in plan.items():
        preview[key] = {
            "approved": entry.approved,
            "need": entry.need,
            "stamp": sent_cache_caption(key),
        }
        if entry.need > 0:
            would_restore += entry.need

    report: dict[str, Any] = {
        "ok": True,
        "execute": execute,
        "target": sent_vault_refill_target() if target is None else target,
        "min_approved": dry_lane_min_approved() if min_approved is None else min_approved,
        "would_restore": would_restore,
        "lanes": preview,
        "skipped_keys": sorted(SENT_VAULT_RECYCLE_SKIP_KEYS),
    }
    if not execute:
        return report
    if not sent_vault_lane_refill_enabled():
        report["skipped"] = True
        report["reason"] = "disabled"
        return report
    if would_restore <= 0:
        report["restored_total"] = 0
        return report

    restored = asyncio.run(
        _apply_sent_vault_refill_async(db, plan, unpause=unpause)
    )
    report["restored"] = restored
    report["restored_total"] = sum(restored.values())
    return report


def refill_pool_from_sent_vault_on_demand_sync(
    db: Session,
    pool_id: int,
    *,
    need: int,
    unpause: bool = False,
) -> int:
    """
    Dry-spell path: when a lane pool has no approved media at send time, pull a random
    vault match (✅+emoji / #tbcc:lane) into approved rotation and return count restored.
    """
    if not sent_vault_dry_spell_refill_enabled():
        return 0
    need_n = max(1, min(60, int(need)))
    key = network_key_for_pool_id(db, int(pool_id))
    if not key or key in SENT_VAULT_RECYCLE_SKIP_KEYS:
        return 0
    pool = db.query(ContentPool).filter(ContentPool.id == int(pool_id)).first()
    if not pool:
        return 0
    approved = (
        db.query(Media).filter(Media.pool_id == int(pool_id), Media.status == "approved").count()
    )
    if approved >= dry_lane_min_approved():
        return 0
    plan = {
        key: SentVaultRefillPlan(
            key=key,
            pool_id=int(pool_id),
            pool_name=str(pool.name or ""),
            approved=int(approved),
            need=need_n,
        )
    }
    try:
        restored = asyncio.run(_apply_sent_vault_refill_async(db, plan, unpause=unpause))
    except Exception as e:
        logger.warning(
            "sent vault dry-spell refill failed pool_id=%s key=%s: %s",
            pool_id,
            key,
            e,
        )
        return 0
    count = int(restored.get(key) or 0)
    if count > 0:
        logger.info(
            "sent vault dry-spell refill pool_id=%s key=%s restored=%s need=%s",
            pool_id,
            key,
            count,
            need_n,
        )
    return count
