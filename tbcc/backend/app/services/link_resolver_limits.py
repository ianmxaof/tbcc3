"""Redis-backed rate limits for bypass provider + per-user quotas."""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Any

logger = logging.getLogger(__name__)


def _redis() -> Any | None:
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, decode_responses=True)
    except Exception as e:
        logger.warning("link_resolver_limits: redis unavailable: %s", e)
        return None


def allow_global_window(*, limit: int, window_sec: float) -> bool:
    """
    Sliding window: at most `limit` events in the last `window_sec` seconds (cluster-wide).
    Returns True if this call is allowed (and records the event).
    """
    if limit <= 0:
        return True
    r = _redis()
    if r is None:
        logger.warning("link_resolver_limits: no REDIS_URL — allowing global bypass (dev only)")
        return True
    key = "tbcc:link_resolver:global_sw"
    now = time.time()
    cutoff = now - window_sec
    member = f"{now}:{random.random()}"
    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(key, "-inf", cutoff)
        pipe.zcard(key)
        cur = pipe.execute()[-1]
        if int(cur) >= limit:
            return False
        pipe = r.pipeline()
        pipe.zadd(key, {member: now})
        pipe.expire(key, int(window_sec) + 5)
        pipe.execute()
        return True
    except Exception as e:
        logger.warning("link_resolver_limits global: %s", e)
        return False


def allow_user_hourly(*, telegram_user_id: int, limit: int) -> bool:
    if limit <= 0:
        return True
    r = _redis()
    if r is None:
        return True
    bucket = int(time.time() // 3600)
    key = f"tbcc:link_resolver:user:{telegram_user_id}:{bucket}"
    try:
        cur_s = r.get(key)
        cur = int(cur_s) if cur_s is not None else 0
        if cur >= limit:
            return False
        n = r.incr(key)
        if n == 1:
            r.expire(key, 7200)
        return int(n) <= limit
    except Exception as e:
        logger.warning("link_resolver_limits user: %s", e)
        return False
