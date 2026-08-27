"""Re-drive Storage Hub media that never got a lane decision.

``run_auto_tag_enrich_for_media`` drops work on the floor in several places: the
focus profile's ``pause_auto_tag`` flag returns early, a Telethon download can
fail, and a worker restart loses whatever was in flight. None of those re-queue
the media, so a deposit can sit forever with no lane decision and no quarantine
card — the operator sees "nothing happened".

This sweep is the backstop. It looks only at the observable end state (a Storage
Hub deposit with no row in ``media_lane_vision_decisions``) so it heals a miss
regardless of which stage lost it.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_CLASSIFIABLE_TYPES = ("photo", "video", "gif")
_LAST_SUCCESS_KEY = "tbcc:enrich_backlog:last_success"


def backlog_enabled() -> bool:
    return (os.getenv("TBCC_ENRICH_BACKLOG_SWEEP") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def backlog_interval_minutes() -> int:
    """Beat crontab is */10; allow override for probe stale threshold."""
    try:
        return max(1, min(120, int(os.getenv("TBCC_ENRICH_BACKLOG_INTERVAL_MIN") or "10")))
    except ValueError:
        return 10


def _redis_client() -> Any:
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
    """Unix ts of last enrich-backlog tick that completed (incl. intentional skips)."""
    try:
        raw = _redis_client().get(_LAST_SUCCESS_KEY)
        if raw is not None:
            return float(raw)
    except Exception:
        logger.debug("enrich_backlog last_success read failed", exc_info=True)
    return 0.0


def mark_last_success() -> None:
    """Stamp Beat tick completion for silent-fail class-2 probes."""
    try:
        _redis_client().set(_LAST_SUCCESS_KEY, str(time.time()))
    except Exception:
        logger.debug("enrich_backlog last_success write failed", exc_info=True)


def backlog_limit() -> int:
    """Cap per tick so a large miss drips through instead of stampeding Telethon.

    Kept small on purpose: a 25-wide sweep put 25 concurrent downloads on the
    Telethon session, tripped the lock-storm detector, and auto-applied
    ``telegram_relief`` — which pauses the very work the sweep just queued.
    """
    try:
        return max(1, min(200, int(os.getenv("TBCC_ENRICH_BACKLOG_LIMIT") or "5")))
    except ValueError:
        return 5


def backlog_stagger_s() -> int:
    """Seconds between queued items, so a tick trickles instead of bursting."""
    try:
        return max(0, min(300, int(os.getenv("TBCC_ENRICH_BACKLOG_STAGGER_S") or "20")))
    except ValueError:
        return 20


def backlog_max_age_hours() -> int:
    """Ignore ancient rows; those predate the pipeline and are not worth downloads."""
    try:
        return max(1, int(os.getenv("TBCC_ENRICH_BACKLOG_MAX_AGE_H") or "72"))
    except ValueError:
        return 72


def find_unclassified_media(db: Session, *, limit: int, max_age_hours: int) -> list[int]:
    """Storage Hub deposits inside the window that have no lane decision yet."""
    from app.models.media import Media
    from app.models.media_lane_vision_decision import MediaLaneVisionDecision
    from app.services.storage_deposit_auto_approve import is_storage_hub_source_label

    cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
    decided = db.query(MediaLaneVisionDecision.media_id)

    rows = (
        db.query(Media.id, Media.source_channel)
        .filter(
            Media.created_at >= cutoff,
            Media.media_type.in_(_CLASSIFIABLE_TYPES),
            ~Media.id.in_(decided),
        )
        .order_by(Media.id.desc())
        # is_storage_hub_source_label is a Python predicate, so over-fetch and
        # filter below rather than trying to express it in SQL.
        .limit(limit * 8)
        .all()
    )

    out: list[int] = []
    for media_id, source_channel in rows:
        if is_storage_hub_source_label(source_channel):
            out.append(int(media_id))
        if len(out) >= limit:
            break
    return out


def telegram_queue_depth() -> int:
    """How many tasks are already waiting on the solo telegram worker."""
    try:
        return int(_redis_client().llen("telegram") or 0)
    except Exception:
        return 0


def backlog_queue_pause_at() -> int:
    """Do not pile more enrich work when the telegram queue is already this deep.

    A 152-deep telegram queue (2026-08-24) made Inbox now toast \"Queued\" then sit
    behind hung downloads for minutes — operator saw nothing happen.
    """
    try:
        return max(5, int(os.getenv("TBCC_ENRICH_BACKLOG_PAUSE_QUEUE") or "15"))
    except ValueError:
        return 15


def run_enrich_backlog_sweep() -> dict[str, object]:
    """Enqueue enrich for missed deposits. Safe to run on a short beat interval."""
    if not backlog_enabled():
        return {"ok": True, "skipped": "disabled"}

    try:
        from app.services.focus_profile import pause_auto_tag_work

        if pause_auto_tag_work():
            # Relief is active for a reason (usually a Telethon lock storm).
            # Re-driving now would just re-skip; the next tick picks it up.
            mark_last_success()
            return {"ok": True, "skipped": "focus_pause_auto_tag"}
    except Exception:
        pass

    depth = telegram_queue_depth()
    pause_at = backlog_queue_pause_at()
    if depth >= pause_at:
        logger.info(
            "enrich backlog sweep skipped — telegram queue depth=%s pause_at=%s",
            depth,
            pause_at,
        )
        mark_last_success()
        return {"ok": True, "skipped": "telegram_queue_deep", "depth": depth}

    from app.database.session import SessionLocal

    db = SessionLocal()
    try:
        media_ids = find_unclassified_media(
            db, limit=backlog_limit(), max_age_hours=backlog_max_age_hours()
        )
    finally:
        db.close()

    if not media_ids:
        mark_last_success()
        return {"ok": True, "queued": 0}

    from app.workers.media_auto_tag_worker import auto_tag_media_enrich

    stagger = backlog_stagger_s()
    queued = 0
    for index, media_id in enumerate(media_ids):
        try:
            auto_tag_media_enrich.apply_async(
                args=[media_id], countdown=index * stagger
            )
            queued += 1
        except Exception:
            logger.warning("enrich backlog enqueue failed media_id=%s", media_id, exc_info=True)

    # Stamp even if some enqueues failed — Beat handler completed.
    mark_last_success()
    logger.info("enrich backlog sweep queued=%s ids=%s", queued, media_ids[:10])
    return {"ok": True, "queued": queued, "media_ids": media_ids}
