"""Backfill sweep: widen searchable tags on already-approved historical media.

``run_auto_tag_enrich_for_media`` only ever runs once, at import time. Media
approved before that pipeline existed (or before a given tag source was
enabled) sits with thin ``media.tags`` forever — which means aof_content_search
ILIKE-matching never finds it. This sweep re-drives the tag-only slice of
enrich (``run_tag_backfill_for_media`` — no routing/approve side effects)
across the existing archive, throttled the same way enrich_backlog paces
Telethon classify downloads.
"""

from __future__ import annotations

import logging
import os
import time
from urllib.parse import urlparse

from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_LAST_SUCCESS_KEY = "tbcc:tag_backfill:last_success"
_DONE_MARKER = '"tag_backfill_done"'


def tag_backfill_sweep_enabled() -> bool:
    """Beat-driven trickle sweep — off by default; the one-time catch-up is a manual script."""
    return (os.getenv("TBCC_TAG_BACKFILL_SWEEP_ENABLED") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def tag_backfill_limit() -> int:
    """Cap per tick — mirrors enrich_backlog's small default to avoid a Telethon lock storm."""
    try:
        return max(1, min(200, int(os.getenv("TBCC_TAG_BACKFILL_LIMIT") or "5")))
    except ValueError:
        return 5


def tag_backfill_stagger_s() -> int:
    try:
        return max(0, min(300, int(os.getenv("TBCC_TAG_BACKFILL_STAGGER_S") or "20")))
    except ValueError:
        return 20


def tag_backfill_thin_tags_chars() -> int:
    """media.tags shorter than this (comma-separated) counts as needing backfill."""
    try:
        return max(1, int(os.getenv("TBCC_TAG_BACKFILL_THIN_CHARS") or "24"))
    except ValueError:
        return 24


def _redis_client():
    import redis

    u = (os.getenv("REDIS_URL") or "").strip()
    if not u:
        raise RuntimeError("REDIS_URL unset")
    p = urlparse(u)
    return redis.Redis(
        host=p.hostname,
        port=p.port or 6379,
        password=p.password,
        db=int((p.path or "/0").lstrip("/") or 0),
    )


def get_last_success_ts() -> float:
    try:
        raw = _redis_client().get(_LAST_SUCCESS_KEY)
        if raw is not None:
            return float(raw)
    except Exception:
        logger.debug("tag_backfill last_success read failed", exc_info=True)
    return 0.0


def mark_last_success() -> None:
    try:
        _redis_client().set(_LAST_SUCCESS_KEY, str(time.time()))
    except Exception:
        logger.debug("tag_backfill last_success write failed", exc_info=True)


def telegram_queue_depth() -> int:
    try:
        return int(_redis_client().llen("telegram") or 0)
    except Exception:
        return 0


def backfill_queue_pause_at() -> int:
    try:
        return max(5, int(os.getenv("TBCC_TAG_BACKFILL_PAUSE_QUEUE") or "15"))
    except ValueError:
        return 15


def find_thin_tag_media(
    db: Session, *, limit: int, pool_id: int | None = None, thin_chars: int | None = None
) -> list[int]:
    """Approved media with short/empty tags that hasn't already run the backfill pass."""
    from app.models.media import Media

    chars = thin_chars if thin_chars is not None else tag_backfill_thin_tags_chars()
    q = db.query(Media.id).filter(
        Media.status == "approved",
        Media.media_type.in_(("photo", "video", "gif")),
        func.length(func.coalesce(Media.tags, "")) < chars,
        ~func.coalesce(Media.classification_json, "").like(f"%{_DONE_MARKER}%"),
    )
    if pool_id is not None:
        q = q.filter(Media.pool_id == pool_id)
    rows = q.order_by(Media.id.desc()).limit(limit).all()
    return [int(r[0]) for r in rows]


def run_tag_backfill_sweep() -> dict[str, object]:
    """Beat tick: enqueue a small, staggered batch. Safe to run on a short interval."""
    if not tag_backfill_sweep_enabled():
        return {"ok": True, "skipped": "disabled"}

    try:
        from app.services.focus_profile import count_active_import_jobs, pause_auto_tag_work

        if pause_auto_tag_work():
            mark_last_success()
            return {"ok": True, "skipped": "focus_pause_auto_tag"}
        if count_active_import_jobs(include_queued=True) > 0:
            mark_last_success()
            return {"ok": True, "skipped": "import_jobs_pending"}
    except Exception:
        pass

    depth = telegram_queue_depth()
    pause_at = backfill_queue_pause_at()
    if depth >= pause_at:
        logger.info("tag backfill sweep skipped — telegram queue depth=%s pause_at=%s", depth, pause_at)
        mark_last_success()
        return {"ok": True, "skipped": "telegram_queue_deep", "depth": depth}

    from app.database.session import SessionLocal

    db = SessionLocal()
    try:
        media_ids = find_thin_tag_media(db, limit=tag_backfill_limit())
    finally:
        db.close()

    if not media_ids:
        mark_last_success()
        return {"ok": True, "queued": 0}

    from app.workers.tag_backfill_worker import backfill_tag_media

    stagger = tag_backfill_stagger_s()
    queued = 0
    for index, media_id in enumerate(media_ids):
        try:
            backfill_tag_media.apply_async(args=[media_id], countdown=index * stagger)
            queued += 1
        except Exception:
            logger.warning("tag backfill enqueue failed media_id=%s", media_id, exc_info=True)

    mark_last_success()
    logger.info("tag backfill sweep queued=%s ids=%s", queued, media_ids[:10])
    return {"ok": True, "queued": queued, "media_ids": media_ids}
