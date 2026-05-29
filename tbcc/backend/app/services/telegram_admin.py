"""
Shared Telethon client for admin imports — avoids connect/disconnect on every request
(large latency) and serializes Telegram I/O to avoid session races.

On "wrong session ID" / connection drops: resets the client once and retries.
Only one process should use admin.session at a time (stop admin_bot / scraper if API imports fail).
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

from telethon import TelegramClient
from telethon.errors.rpcerrorlist import AuthKeyDuplicatedError, ImageProcessFailedError

from app.services.telegram_storage import TelegramStorage
from app.utils.telethon_session import (
    admin_session_stem,
    configure_telethon_sqlite_session,
    graceful_telethon_disconnect,
    poster_session_stem,
    sqlite_busy_timeout_ms,
    telethon_sessions_share_file,
)

logger = logging.getLogger(__name__)

_init_lock = asyncio.Lock()
_import_lock = asyncio.Lock()
_client: TelegramClient | None = None

T = TypeVar("T")


def _telegram_session_path() -> str:
    """Return stable Telethon session path shared across processes."""
    return admin_session_stem()


def _telegram_io_max_attempts() -> int:
    raw = (os.getenv("TBCC_TELEGRAM_IO_MAX_ATTEMPTS") or "8").strip()
    try:
        return max(1, min(20, int(raw)))
    except ValueError:
        return 8


def _telegram_io_backoff_seconds(attempt: int) -> float:
    """attempt is 0-based index of the failed try before retry."""
    return min(15.0, 0.5 * (2**attempt))


def import_lock() -> asyncio.Lock:
    """Serialize Telegram sends + DB commits that touch the same client."""
    return _import_lock


def friendly_telegram_error(exc: BaseException) -> str:
    """Actionable message for API / extension clients."""
    msg = str(exc).strip()
    low = msg.lower()
    if "wrong session id" in low or "security error while unpacking" in low:
        return (
            "Telegram session conflict (wrong session ID). "
            "Stop other TBCC processes that use admin.session (admin_bot, scraper_bot, Celery worker), "
            "restart the API, then retry. If it persists: cd tbcc/backend && python scripts/login_telethon_sessions.py"
        )
    if isinstance(exc, AuthKeyDuplicatedError) or "auth key duplicated" in low:
        return (
            "Telegram auth key duplicated — two programs logged in with admin.session at once. "
            "Stop admin_bot/scraper/Celery, restart the API, retry."
        )
    if "not logged in" in low or "not authorized" in low or "user is not authorized" in low:
        return (
            "Telegram admin session is not logged in (admin.session). "
            "From tbcc/backend run: python scripts/login_telethon_sessions.py"
        )
    if "database is locked" in low or "sqlite_busy" in low:
        poster = Path(poster_session_stem()).name
        if telethon_sessions_share_file():
            return (
                "Telegram session file is locked — admin and poster workers share the same "
                f"{Path(_telegram_session_path()).name}.session file. "
                f"Set TBCC_POSTER_TELEGRAM_SESSION={poster} and TBCC_POSTER_AUTO_COPY_ADMIN_SESSION=1 "
                "in tbcc/.env, restart API + Celery, then retry."
            )
        return (
            "Telegram session file is locked (another TBCC process is using "
            f"{Path(_telegram_session_path()).name}.session). "
            "Stop scraper_bot briefly, or wait — the API retries automatically. "
            f"Poster workers should use a separate session ({poster}.session)."
        )
    if "connection to telegram failed" in low or "server closed the connection" in low:
        return f"Telegram connection dropped — retry in a few seconds. ({msg[:120]})"
    if "sticker is too big" in low or "video sticker is too big" in low:
        return (
            "Telegram rejected a tile: each video sticker must be ≤ 256 KB. "
            "Restart the API, then run Split + publish again (TBCC auto-compresses tiles). "
            "If it still fails, use a 2s loop, higher CRF, or Static."
        )
    return f"Telegram send failed: {msg[:220]}"


def _is_telethon_recoverable_error(err: BaseException) -> bool:
    if isinstance(err, ImageProcessFailedError):
        return False
    if isinstance(err, (AuthKeyDuplicatedError, ConnectionError, TimeoutError, OSError)):
        return True
    msg = str(err).lower()
    if "wrong session id" in msg or "security error while unpacking" in msg:
        return True
    if "auth key duplicated" in msg:
        return True
    if "connection to telegram failed" in msg:
        return True
    if "server closed the connection" in msg:
        return True
    if "database is locked" in msg:
        return True
    if "event loop must not change" in msg:
        return True
    return False


async def reset_admin_client() -> None:
    global _client
    async with _init_lock:
        c = _client
        _client = None
    if c is not None:
        await graceful_telethon_disconnect(c)


async def _connect_admin_client() -> TelegramClient:
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        raise RuntimeError("Telegram API not configured")
    stem = _telegram_session_path()
    client = TelegramClient(stem, int(os.environ["API_ID"]), os.environ["API_HASH"])
    await client.connect()
    configure_telethon_sqlite_session(client)
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError(
            f"Telegram admin session is not logged in ({Path(stem).name}.session). "
            "From tbcc/backend run: python scripts/login_telethon_sessions.py"
        )
    return client


async def _ensure_admin_client() -> TelegramClient:
    """Single-flight connect/reconnect — never open admin.session from parallel coroutines."""
    global _client
    async with _init_lock:
        if _client is not None and _client.is_connected():
            return _client
        if _client is not None:
            try:
                await _client.connect()
                configure_telethon_sqlite_session(_client)
                if await _client.is_user_authorized():
                    return _client
            except Exception:
                logger.warning("admin reconnect failed; resetting session client", exc_info=True)
            old = _client
            _client = None
            try:
                await old.disconnect()
            except Exception:
                pass
            await asyncio.sleep(0.5)
        _client = await _connect_admin_client()
        return _client


async def get_telegram_storage() -> TelegramStorage:
    """Return TelegramStorage backed by a long-lived client (lazy-init)."""
    client = await _ensure_admin_client()
    return TelegramStorage(client)


async def run_telegram_io(fn: Callable[[TelegramStorage], Awaitable[T]]) -> T:
    """
    Run ``await fn(storage)`` under import_lock.
    Retries with backoff on session/connection/SQLite lock errors (TBCC_TELEGRAM_IO_MAX_ATTEMPTS).
    """
    last_err: BaseException | None = None
    max_attempts = _telegram_io_max_attempts()
    for attempt in range(max_attempts):
        try:
            async with _import_lock:
                storage = await get_telegram_storage()
                return await fn(storage)
        except Exception as e:
            last_err = e
            if attempt + 1 < max_attempts and _is_telethon_recoverable_error(e):
                delay = _telegram_io_backoff_seconds(attempt)
                logger.warning(
                    "Telegram admin I/O failed (attempt %s/%s): %s — reset client, retry in %.1fs",
                    attempt + 1,
                    max_attempts,
                    e,
                    delay,
                )
                await reset_admin_client()
                await asyncio.sleep(delay)
                continue
            raise
    if last_err is not None:
        raise last_err
    raise RuntimeError("Telegram I/O failed without exception")


async def run_telegram_client_io(fn: Callable[[TelegramClient], Awaitable[T]]) -> T:
    """Same retry/lock semantics as run_telegram_io but for raw Telethon client callbacks."""
    last_err: BaseException | None = None
    max_attempts = _telegram_io_max_attempts()
    for attempt in range(max_attempts):
        try:
            async with _import_lock:
                client = await _ensure_admin_client()
                return await fn(client)
        except Exception as e:
            last_err = e
            if attempt + 1 < max_attempts and _is_telethon_recoverable_error(e):
                delay = _telegram_io_backoff_seconds(attempt)
                logger.warning(
                    "Telegram client I/O failed (attempt %s/%s): %s — reset client, retry in %.1fs",
                    attempt + 1,
                    max_attempts,
                    e,
                    delay,
                )
                await reset_admin_client()
                await asyncio.sleep(delay)
                continue
            raise
    if last_err is not None:
        raise last_err
    raise RuntimeError("Telegram client I/O failed without exception")


async def check_admin_telegram_session() -> dict:
    """Lightweight session probe for /health/telegram."""
    try:
        async def _probe(client: TelegramClient):
            return await client.get_me()

        me = await run_telegram_client_io(_probe)
        username = getattr(me, "username", None) or ""
        return {
            "ok": True,
            "user_id": me.id,
            "username": username,
            "session": Path(_telegram_session_path()).name,
            "poster_session": Path(poster_session_stem()).name,
            "sessions_share_file": telethon_sessions_share_file(),
            "sqlite_busy_timeout_ms": sqlite_busy_timeout_ms(),
        }
    except Exception as e:
        return {"ok": False, "error": friendly_telegram_error(e)}


async def get_telegram_client() -> TelegramClient:
    """
    Raw Telethon client. Prefer ``run_telegram_io`` for downloads/sends so work is serialized
    and session reconnect does not run concurrently (SQLite session lock).
    """
    return await _ensure_admin_client()


async def disconnect_admin() -> None:
    await reset_admin_client()
