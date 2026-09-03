"""Short-lived continuation state for "still want more?" search follow-ups.

Telegram callback_data caps out at 64 bytes, so a full query + surface +
already-shown media id list cannot ride in the button itself. This stores
that state in Redis behind a short token the callback carries instead.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from typing import Any

logger = logging.getLogger(__name__)

_REDIS_PREFIX = "tbcc:aof_search:sess"
_MAX_SHOWN_IDS = 200


def _redis_client():
    from app.services.content_signals import _redis_client as client

    return client()


def session_ttl_s() -> int:
    try:
        return max(60, min(3600, int(os.getenv("TBCC_AOF_SEARCH_SESSION_TTL_S") or "900")))
    except ValueError:
        return 900


def _key(token: str) -> str:
    return f"{_REDIS_PREFIX}:{token}"


def start_search_session(
    *, user_id: int, surface: str, query: str, shown_ids: list[int]
) -> str | None:
    """Create a continuation session, return its token (None if Redis unavailable)."""
    r = _redis_client()
    if not r:
        return None
    token = secrets.token_urlsafe(8)
    payload = {
        "user_id": int(user_id),
        "surface": surface,
        "query": query,
        "shown_ids": [int(x) for x in shown_ids][-_MAX_SHOWN_IDS:],
        "started_at": time.time(),
    }
    try:
        r.setex(_key(token), session_ttl_s(), json.dumps(payload))
    except Exception:
        logger.debug("start_search_session write failed", exc_info=True)
        return None
    return token


def get_search_session(token: str) -> dict[str, Any] | None:
    r = _redis_client()
    if not r:
        return None
    try:
        raw = r.get(_key(token))
    except Exception:
        logger.debug("get_search_session read failed", exc_info=True)
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def extend_search_session(token: str, *, new_shown_ids: list[int]) -> None:
    r = _redis_client()
    if not r:
        return
    session = get_search_session(token)
    if not session:
        return
    shown = list(session.get("shown_ids") or [])
    for mid in new_shown_ids:
        mid = int(mid)
        if mid not in shown:
            shown.append(mid)
    session["shown_ids"] = shown[-_MAX_SHOWN_IDS:]
    try:
        r.setex(_key(token), session_ttl_s(), json.dumps(session))
    except Exception:
        logger.debug("extend_search_session write failed", exc_info=True)
