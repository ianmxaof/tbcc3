"""Stash last user photo + settings so they can redo a reveal without re-uploading."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_MEM: dict[int, dict[str, Any]] = {}
_TTL_SEC = 60 * 60 * 24


def _redis() -> Any | None:
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, decode_responses=True)
    except Exception as e:
        logger.warning("companion_last_reveal: redis unavailable: %s", e)
        return None


def _key(user_id: int) -> str:
    return f"tbcc:companion:last_reveal:{user_id}"


def save_last_reveal(
    user_id: int,
    *,
    file_id: str,
    filename: str,
    media_mode: str = "photo",
) -> None:
    payload = json.dumps(
        {
            "file_id": (file_id or "").strip(),
            "filename": (filename or "photo.jpg").strip() or "photo.jpg",
            "media_mode": (media_mode or "photo").strip().lower(),
        }
    )
    r = _redis()
    if r is not None:
        try:
            r.setex(_key(int(user_id)), _TTL_SEC, payload)
            return
        except Exception as e:
            logger.warning("companion_last_reveal save failed: %s", e)
    _MEM[int(user_id)] = json.loads(payload)


def get_last_reveal(user_id: int) -> dict[str, Any] | None:
    uid = int(user_id)
    r = _redis()
    if r is not None:
        try:
            raw = r.get(_key(uid))
            if raw:
                data = json.loads(raw)
                return data if isinstance(data, dict) and data.get("file_id") else None
        except Exception as e:
            logger.warning("companion_last_reveal get failed: %s", e)
    data = _MEM.get(uid)
    return data if data and data.get("file_id") else None
