"""Inbox intake — quarantine album cards in gatekeeper Q&A subtopic."""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_storage_hub_map import (
    INBOX_CHANNEL_IDENT,
    INBOX_TOPIC_ID,
    STORAGE_HUB_IDENT,
)
from app.services.intake_scheduler import get_album_size
from app.services.quarantine_batch_review import (
    post_quarantine_batch,
)

logger = logging.getLogger(__name__)

PENDING_KEY = "tbcc:inbox:quarantine:pending"


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def inbox_intake_enabled() -> bool:
    return (os.getenv("TBCC_INBOX_INTAKE_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def is_inbox_source_label(source_channel: str | None) -> bool:
    raw = (source_channel or "").strip().lower()
    if not raw:
        return False
    if f"#topic:{INBOX_TOPIC_ID}" in raw:
        return True
    ch = INBOX_CHANNEL_IDENT.lstrip("-")
    return INBOX_CHANNEL_IDENT in raw or ch in raw.replace("telegram:", "")


def is_inbox_media(media: Any) -> bool:
    return is_inbox_source_label(getattr(media, "source_channel", None))


def _review_dest_for_media(media: Any) -> dict[str, Any]:
    """Post review cards into the gatekeeper Q&A subtopic (APPROVE/DENY | INTAKE).

    Topic id 1 is General renamed to Q&A — Bot API rejects message_thread_id=1
    (``message thread not found``). Omit the thread so the card lands in Q&A.
    """
    from app.data.aof_storage_hub_map import GATEKEEPER_REVIEW_TOPIC_ID, INBOX_CHANNEL_IDENT
    from app.utils.telegram_forum import bot_api_forum_thread_id

    src = (getattr(media, "source_channel", None) or "").strip()
    if INBOX_CHANNEL_IDENT.lstrip("-") in src.replace("telegram:", ""):
        return {"chat_id": int(INBOX_CHANNEL_IDENT), "message_thread_id": None}
    raw_tid = int(GATEKEEPER_REVIEW_TOPIC_ID) if GATEKEEPER_REVIEW_TOPIC_ID else INBOX_TOPIC_ID
    return {"chat_id": int(STORAGE_HUB_IDENT), "message_thread_id": bot_api_forum_thread_id(raw_tid)}


def inbox_quarantine_buffer_count() -> int:
    try:
        return int(_redis().llen(PENDING_KEY))
    except Exception:
        return 0


def queue_inbox_quarantine_media(media_id: int) -> dict[str, Any]:
    """Buffer quarantined inbox media; flush album when batch is full."""
    if not inbox_intake_enabled():
        return {"queued": False, "reason": "disabled"}
    mid = int(media_id)
    try:
        r = _redis()
        r.rpush(PENDING_KEY, str(mid))
        pending = int(r.llen(PENDING_KEY))
        # Inbox cards must appear after a single drop (Inbox now), not wait for 5.
        album_size = 1
        if pending >= album_size:
            ids = [int(x) for x in (r.lrange(PENDING_KEY, 0, album_size - 1) or [])]
            r.ltrim(PENDING_KEY, album_size, -1)
            return {"queued": True, "flushing": True, "media_ids": ids, "pending_left": pending - album_size}
        return {"queued": True, "flushing": False, "pending": pending, "album_size": album_size}
    except Exception as e:
        logger.warning("inbox quarantine queue failed media_id=%s: %s", mid, e)
        return {"queued": False, "error": str(e)[:200]}


def flush_pending_inbox_quarantine(*, force: bool = False) -> dict[str, Any]:
    """Post any buffered inbox quarantine items as one album card."""
    if not inbox_intake_enabled():
        return {"ok": False, "reason": "disabled"}
    try:
        r = _redis()
        pending = int(r.llen(PENDING_KEY))
        if pending < 1:
            return {"ok": True, "skipped": True, "reason": "empty"}
        album_size = get_album_size()
        if not force and pending < album_size:
            return {"ok": True, "skipped": True, "reason": "below_album_size", "pending": pending}
        take = min(pending, album_size) if not force else min(pending, album_size)
        if force and pending > 0:
            take = min(pending, album_size)
        ids = [int(x) for x in (r.lrange(PENDING_KEY, 0, take - 1) or [])]
        r.ltrim(PENDING_KEY, take, -1)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}

    from app.database.session import SessionLocal

    with SessionLocal() as db:
        out = post_inbox_quarantine_batch(db, ids)
    if not out.get("ok") and ids:
        try:
            r = _redis()
            for mid in reversed(ids):
                r.lpush(PENDING_KEY, str(mid))
        except Exception:
            logger.warning("inbox quarantine restore failed ids=%s", ids, exc_info=True)
    return out


def post_inbox_quarantine_batch(db: Session, media_ids: list[int]) -> dict[str, Any]:
    """Copy inbox media previews + post one control card with batch approve/reject."""
    from app.models.media import Media

    ids = [int(x) for x in media_ids if int(x) > 0]
    if not ids:
        return {"ok": False, "reason": "empty"}

    first = db.query(Media).filter(Media.id.in_(ids)).first()
    if not first:
        return {"ok": False, "reason": "not_found"}

    dest = _review_dest_for_media(first)
    return post_quarantine_batch(
        db,
        ids,
        dest=dest,
        label="INBOX QUARANTINE",
        lane_key="inbox",
    )
