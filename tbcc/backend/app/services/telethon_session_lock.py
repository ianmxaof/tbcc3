"""
Cross-process locks for Telethon session SQLite files.

The API (uvicorn) and Celery (telegram queue) are separate processes — asyncio locks
do not span them. Redis locks queue work instead of failing with "database is locked".
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_ADMIN_LOCK_KEY = "tbcc:lock:admin_telegram_session"
_IMPORT_LOCK_KEY = "tbcc:lock:import_telegram_session"
_RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
  return redis.call("del", KEYS[1])
else
  return 0
end
"""


def _redis_url() -> str:
    return (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()


def _lock_timeout_s() -> float:
    raw = (os.getenv("TBCC_TELEGRAM_LOCK_TIMEOUT_S") or "300").strip()
    try:
        return max(30.0, min(1800.0, float(raw)))
    except ValueError:
        return 300.0


def _poll_interval_s() -> float:
    raw = (os.getenv("TBCC_TELEGRAM_LOCK_POLL_S") or "0.35").strip()
    try:
        return max(0.1, min(2.0, float(raw)))
    except ValueError:
        return 0.35


def _redis_client():
    import redis

    return redis.from_url(_redis_url(), decode_responses=True)


def _acquire_session_lock(
    lock_key: str,
    *,
    label: str,
    timeout_s: float | None = None,
    stuck_hint: str,
) -> str:
    timeout = _lock_timeout_s() if timeout_s is None else max(1.0, min(1800.0, float(timeout_s)))
    poll = _poll_interval_s()
    token = uuid.uuid4().hex
    deadline = time.monotonic() + timeout
    r = _redis_client()
    ttl = int(timeout) + 120
    waited_logged = False
    while time.monotonic() < deadline:
        try:
            if r.set(lock_key, token, nx=True, ex=ttl):
                if waited_logged:
                    logger.info("%s Telethon session lock acquired after wait", label)
                return token
        except Exception as e:
            logger.warning("Redis session lock unavailable (%s) — proceeding without lock", e)
            return token
        if not waited_logged:
            if timeout <= 15:
                logger.info(
                    "waiting for %s Telethon session (interactive; up to %.0fs)",
                    label,
                    timeout,
                )
            else:
                logger.info(
                    "waiting for %s Telethon session (another TBCC task is using it; up to %.0fs)",
                    label,
                    timeout,
                )
            waited_logged = True
        time.sleep(poll)
    raise TimeoutError(
        f"Timed out after {timeout:.0f}s waiting for the Telegram {label} session. {stuck_hint}"
    )


def _release_session_lock(lock_key: str, token: str) -> None:
    if not token:
        return
    try:
        r = _redis_client()
        r.eval(_RELEASE_LUA, 1, lock_key, token)
    except Exception:
        logger.debug("release %s session lock failed", lock_key, exc_info=True)


def acquire_admin_session_lock(timeout_s: float | None = None) -> str:
    """Block until this process may open admin.session (or timeout)."""
    return _acquire_session_lock(
        _ADMIN_LOCK_KEY,
        label="admin",
        timeout_s=timeout_s,
        stuck_hint=(
            "Another TBCC task may be stuck (Celery import queue). "
            "Check TBCC-Celery logs or restart TBCC-Celery."
        ),
    )


def release_admin_session_lock(token: str) -> None:
    _release_session_lock(_ADMIN_LOCK_KEY, token)


def acquire_import_session_lock(timeout_s: float | None = None) -> str:
    """Block until this process may open the dedicated import session (or timeout)."""
    return _acquire_session_lock(
        _IMPORT_LOCK_KEY,
        label="import",
        timeout_s=timeout_s,
        stuck_hint=(
            "Another import job may be stuck on TBCC-Celery (telegram queue). "
            "Check TBCC-Celery logs or restart TBCC-Celery."
        ),
    )


def release_import_session_lock(token: str) -> None:
    _release_session_lock(_IMPORT_LOCK_KEY, token)


@contextmanager
def admin_session_redis_lock():
    token = acquire_admin_session_lock()
    try:
        yield
    finally:
        release_admin_session_lock(token)


@contextmanager
def import_session_redis_lock():
    token = acquire_import_session_lock()
    try:
        yield
    finally:
        release_import_session_lock(token)


async def acquire_admin_session_lock_async(timeout_s: float | None = None):
    import asyncio

    return await asyncio.to_thread(acquire_admin_session_lock, timeout_s)


async def release_admin_session_lock_async(token: str) -> None:
    import asyncio

    await asyncio.to_thread(release_admin_session_lock, token)


async def acquire_import_session_lock_async(timeout_s: float | None = None):
    import asyncio

    return await asyncio.to_thread(acquire_import_session_lock, timeout_s)


async def release_import_session_lock_async(token: str) -> None:
    import asyncio

    await asyncio.to_thread(release_import_session_lock, token)
