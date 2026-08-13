"""Stash a Telegram file_id until Stars payment completes."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_PENDING_TTL_SEC = 60 * 30
_MEM: dict[int, dict[str, Any]] = {}


def _redis() -> Any | None:
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, decode_responses=True)
    except Exception as e:
        logger.warning("companion_pending_photo: redis unavailable: %s", e)
        return None


def _key(user_id: int) -> str:
    return f"tbcc:companion:pending_photo:{user_id}"


def save_pending_photo(
    *,
    user_id: int,
    chat_id: int,
    file_id: str,
    filename: str,
    media_type: str = "photo",
) -> None:
    payload = json.dumps(
        {
            "user_id": int(user_id),
            "chat_id": int(chat_id),
            "file_id": file_id,
            "filename": filename or "photo.jpg",
            "media_type": (media_type or "photo").strip().lower(),
        }
    )
    r = _redis()
    if r is not None:
        try:
            r.setex(_key(int(user_id)), _PENDING_TTL_SEC, payload)
            return
        except Exception as e:
            logger.warning("companion_pending_photo save failed: %s", e)
    _MEM[int(user_id)] = json.loads(payload)


def pop_pending_photo(user_id: int) -> dict[str, Any] | None:
    uid = int(user_id)
    r = _redis()
    if r is not None:
        try:
            raw = r.get(_key(uid))
            if raw:
                r.delete(_key(uid))
                return json.loads(raw)
        except Exception as e:
            logger.warning("companion_pending_photo pop failed: %s", e)
    data = _MEM.pop(uid, None)
    return data
