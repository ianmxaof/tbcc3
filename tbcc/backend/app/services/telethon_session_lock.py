"""
Cross-process locks for Telethon session SQLite files.

The API (uvicorn) and Celery (telegram queue) are separate processes — asyncio locks
do not span them. Redis locks queue work instead of failing with "database is locked".

Copied session files (admin_poster, admin_import, admin_album from admin.session) share
one Telegram auth key — only one MTProto connection may be live at a time. Per-file locks
alone cause "wrong session ID" / "very old message" storms when poster + import + admin
connect concurrently. TBCC_TELEGRAM_ACCOUNT_LOCK (default on) adds a global account lock
nested under each session lock.
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
_POSTER_LOCK_KEY = "tbcc:lock:poster_telegram_session"
_ACCOUNT_LOCK_KEY = "tbcc:lock:telegram_account_mtproto"
# session lock token -> account lock token (release both on session release)
_account_lock_by_session: dict[str, str] = {}
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


def telegram_account_lock_enabled() -> bool:
    """
    When True, all Telethon session locks also hold tbcc:lock:telegram_account_mtproto.
    Disable only if each session file was logged in separately (distinct auth keys).
    """
    raw = (os.getenv("TBCC_TELEGRAM_ACCOUNT_LOCK") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def acquire_telegram_account_lock(timeout_s: float | None = None) -> str:
    """Block until this process may open any Telethon MTProto connection for the account."""
    return _acquire_session_lock(
        _ACCOUNT_LOCK_KEY,
        label="account",
        timeout_s=timeout_s,
        stuck_hint=(
            "Another TBCC worker is connected to Telegram (admin/import/poster/album). "
            "Wait for it to finish or restart TBCC-Celery and TBCC-Celery-Post."
        ),
    )


def release_telegram_account_lock(token: str) -> None:
    _release_session_lock(_ACCOUNT_LOCK_KEY, token)


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


def _acquire_nested_session_lock(
    lock_key: str,
    *,
    label: str,
    timeout_s: float | None,
    stuck_hint: str,
) -> str:
    account_token = ""
    if telegram_account_lock_enabled():
        account_token = acquire_telegram_account_lock(timeout_s)
    try:
        session_token = _acquire_session_lock(
            lock_key,
            label=label,
            timeout_s=timeout_s,
            stuck_hint=stuck_hint,
        )
        if account_token:
            _account_lock_by_session[session_token] = account_token
        return session_token
    except Exception:
        if account_token:
            release_telegram_account_lock(account_token)
        raise


def _release_nested_session_lock(lock_key: str, token: str) -> None:
    account_token = _account_lock_by_session.pop(token, "")
    _release_session_lock(lock_key, token)
    if account_token:
        release_telegram_account_lock(account_token)


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
    return _acquire_nested_session_lock(
        _ADMIN_LOCK_KEY,
        label="admin",
        timeout_s=timeout_s,
        stuck_hint=(
            "Another TBCC task may be stuck (Celery import queue). "
            "Check TBCC-Celery logs or restart TBCC-Celery."
        ),
    )


def release_admin_session_lock(token: str) -> None:
    _release_nested_session_lock(_ADMIN_LOCK_KEY, token)


def acquire_import_session_lock(timeout_s: float | None = None) -> str:
    """Block until this process may open the dedicated import session (or timeout)."""
    return _acquire_nested_session_lock(
        _IMPORT_LOCK_KEY,
        label="import",
        timeout_s=timeout_s,
        stuck_hint=(
            "Another import job may be stuck on TBCC-Celery (telegram queue). "
            "Check TBCC-Celery logs or restart TBCC-Celery."
        ),
    )


def release_import_session_lock(token: str) -> None:
    _release_nested_session_lock(_IMPORT_LOCK_KEY, token)


def acquire_poster_session_lock(timeout_s: float | None = None) -> str:
    """Block until this process may open admin_poster.session (or timeout)."""
    return _acquire_nested_session_lock(
        _POSTER_LOCK_KEY,
        label="poster",
        timeout_s=timeout_s,
        stuck_hint=(
            "Another scheduled post or stats fetch may be using admin_poster.session. "
            "Check TBCC-Celery-Post logs or restart TBCC-Celery-Post."
        ),
    )


def release_poster_session_lock(token: str) -> None:
    _release_nested_session_lock(_POSTER_LOCK_KEY, token)


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


@contextmanager
def poster_session_redis_lock():
    token = acquire_poster_session_lock()
    try:
        yield
    finally:
        release_poster_session_lock(token)


@contextmanager
def telegram_account_redis_lock():
    token = acquire_telegram_account_lock()
    try:
        yield
    finally:
        release_telegram_account_lock(token)


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


async def acquire_poster_session_lock_async(timeout_s: float | None = None):
    import asyncio

    return await asyncio.to_thread(acquire_poster_session_lock, timeout_s)


async def release_poster_session_lock_async(token: str) -> None:
    import asyncio

    await asyncio.to_thread(release_poster_session_lock, token)


async def acquire_telegram_account_lock_async(timeout_s: float | None = None):
    import asyncio

    return await asyncio.to_thread(acquire_telegram_account_lock, timeout_s)


async def release_telegram_account_lock_async(token: str) -> None:
    import asyncio

    await asyncio.to_thread(release_telegram_account_lock, token)
