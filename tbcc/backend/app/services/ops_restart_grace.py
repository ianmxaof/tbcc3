"""Suppress ops alert toasts while TBCC-Backend is restarting (expected downstream blips)."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

REDIS_KEY = "tbcc:ops:backend_restart_grace_until"


def _redis_client():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def restart_grace_seconds() -> int:
    raw = (os.getenv("TBCC_BACKEND_RESTART_GRACE_S") or "120").strip()
    try:
        return max(30, min(600, int(raw)))
    except ValueError:
        return 120


def restart_grace_tail_seconds() -> int:
    raw = (os.getenv("TBCC_BACKEND_RESTART_GRACE_TAIL_S") or "20").strip()
    try:
        return max(0, min(120, int(raw)))
    except ValueError:
        return 20


def mark_backend_restart_grace(*, seconds: int | None = None, reason: str = "") -> dict[str, Any]:
    """Call before stopping TBCC-Backend — downstream API errors are expected, not urgent."""
    duration = restart_grace_seconds() if seconds is None else max(10, min(600, int(seconds)))
    until = time.time() + duration
    try:
        r = _redis_client()
        r.set(REDIS_KEY, str(until), ex=duration + 60)
    except Exception as e:
        logger.debug("mark_backend_restart_grace failed: %s", e)
        return {"ok": False, "error": str(e)[:200]}
    return {
        "ok": True,
        "active": True,
        "until_unix": until,
        "seconds": duration,
        "reason": (reason or "backend_restart")[:200],
    }


def clear_backend_restart_grace(*, tail_seconds: int | None = None) -> dict[str, Any]:
    """
    Call after /health is OK. Optional short tail keeps suppressing straggler hub lines.
    """
    tail = restart_grace_tail_seconds() if tail_seconds is None else max(0, min(120, int(tail_seconds)))
    if tail > 0:
        return mark_backend_restart_grace(seconds=tail, reason="restart_tail")
    try:
        r = _redis_client()
        r.delete(REDIS_KEY)
    except Exception as e:
        logger.debug("clear_backend_restart_grace failed: %s", e)
        return {"ok": False, "error": str(e)[:200]}
    return {"ok": True, "active": False}


def backend_restart_grace_active() -> bool:
    try:
        r = _redis_client()
        raw = r.get(REDIS_KEY)
        if not raw:
            return False
        return time.time() < float(raw)
    except Exception:
        return False


def restart_grace_public_snapshot() -> dict[str, Any]:
    active = backend_restart_grace_active()
    out: dict[str, Any] = {"active": active}
    if not active:
        return out
    try:
        r = _redis_client()
        raw = r.get(REDIS_KEY)
        if raw:
            until = float(raw)
            out["until_unix"] = until
            out["remaining_s"] = max(0, int(until - time.time()))
    except Exception:
        pass
    return out
