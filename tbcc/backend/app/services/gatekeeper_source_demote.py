"""Source reject streak tracking and SCRP demotion on operator reject."""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.data.media_gatekeeper_spec import SOURCE_DEMOTE_REJECT_STREAK

logger = logging.getLogger(__name__)

_REDIS_STREAK_PREFIX = "tbcc:gatekeeper:reject_streak:"
_REDIS_BANNED_KEY = "tbcc:gatekeeper:banned_sources"
_local_streak: dict[str, int] = {}
_local_banned: set[int] = set()


def demote_streak_threshold() -> int:
    raw = (os.getenv("TBCC_GATEKEEPER_DEMOTE_STREAK") or str(SOURCE_DEMOTE_REJECT_STREAK)).strip()
    try:
        return max(1, min(50, int(raw)))
    except ValueError:
        return SOURCE_DEMOTE_REJECT_STREAK


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )


def _streak_key(chat_id: int) -> str:
    return f"{_REDIS_STREAK_PREFIX}{int(chat_id)}"


def is_source_banned(chat_id: int | None) -> bool:
    if chat_id is None:
        return False
    cid = int(chat_id)
    from app.data.aof_scrape_inbound_map import SKIP_INBOUND_CHAT_IDS

    if cid in SKIP_INBOUND_CHAT_IDS:
        return True
    if cid in _local_banned:
        return True
    try:
        r = _redis()
        return bool(r.sismember(_REDIS_BANNED_KEY, str(cid)))
    except Exception:
        return cid in _local_banned


def ban_source_chat_id(chat_id: int) -> None:
    cid = int(chat_id)
    _local_banned.add(cid)
    try:
        r = _redis()
        r.sadd(_REDIS_BANNED_KEY, str(cid))
    except Exception:
        logger.debug("ban_source redis unavailable chat_id=%s", cid, exc_info=True)


def get_reject_streak(chat_id: int | None) -> int:
    if chat_id is None:
        return 0
    key = _streak_key(int(chat_id))
    try:
        r = _redis()
        raw = r.get(key)
        return int(raw or 0)
    except Exception:
        return int(_local_streak.get(key, 0))


def reset_reject_streak(chat_id: int | None) -> None:
    if chat_id is None:
        return
    key = _streak_key(int(chat_id))
    _local_streak.pop(key, None)
    try:
        r = _redis()
        r.delete(key)
    except Exception:
        pass


def increment_reject_streak(chat_id: int | None) -> int:
    if chat_id is None:
        return 0
    key = _streak_key(int(chat_id))
    try:
        r = _redis()
        return int(r.incr(key))
    except Exception:
        n = _local_streak.get(key, 0) + 1
        _local_streak[key] = n
        return n


def resolve_source_chat_id(db: Session, media: Any) -> int | None:
    """Numeric Telegram channel id for streak/demote (scrape identifier or parsed label)."""
    from app.services.media_gatekeeper import parse_source_channel_id

    raw = getattr(media, "source_channel", None)
    ident = parse_source_channel_id(str(raw) if raw else None)
    if ident is not None:
        return ident
    if raw and not str(raw).startswith("telegram:"):
        return parse_source_channel_id(str(raw))
    return None


def demote_scrape_source(db: Session, chat_id: int) -> dict[str, Any]:
    """Deactivate SCRP Source row and ban chat id from future ingest."""
    from app.models.source import Source

    ident = str(int(chat_id))
    rows = (
        db.query(Source)
        .filter(Source.identifier == ident, Source.source_type == "telegram_channel")
        .all()
    )
    deactivated = 0
    for row in rows:
        if row.active:
            row.active = False
            deactivated += 1
    if deactivated:
        db.commit()
    ban_source_chat_id(int(chat_id))
    logger.warning(
        "gatekeeper demoted source chat_id=%s deactivated=%s",
        chat_id,
        deactivated,
    )
    return {
        "chat_id": int(chat_id),
        "sources_deactivated": deactivated,
        "banned": True,
    }


def record_operator_reject(db: Session, media: Any) -> dict[str, Any]:
    """Increment streak; demote source when threshold reached."""
    chat_id = resolve_source_chat_id(db, media)
    if chat_id is None:
        return {"streak": 0, "demoted": False, "reason": "no_source_chat_id"}
    streak = increment_reject_streak(chat_id)
    out: dict[str, Any] = {"chat_id": chat_id, "streak": streak, "demoted": False}
    if streak >= demote_streak_threshold():
        out["demoted"] = True
        out["demote"] = demote_scrape_source(db, chat_id)
        reset_reject_streak(chat_id)
    return out


def record_operator_approve(db: Session, media: Any) -> None:
    chat_id = resolve_source_chat_id(db, media)
    reset_reject_streak(chat_id)
