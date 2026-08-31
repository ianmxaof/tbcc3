"""
Shared Telethon client for admin imports — avoids connect/disconnect on every request
(large latency) and serializes Telegram I/O to avoid session races.

On "wrong session ID" / connection drops: resets the client once and retries.
Cross-process access is serialized via Redis (TBCC_TELEGRAM_LOCK_*); Celery and the API queue automatically.
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
    album_composer_session_stem,
    configure_telethon_sqlite_session,
    graceful_telethon_disconnect,
    import_session_stem,
    import_sessions_share_admin_file,
    poster_session_stem,
    sqlite_busy_timeout_ms,
    telethon_disconnect_admin_after_io,
    telethon_disconnect_import_after_io,
    telethon_sessions_share_file,
)

logger = logging.getLogger(__name__)

# asyncio.Lock() must be created on the running loop — loot delivery uses asyncio.run() in a worker thread.
_loop_locks: dict[tuple[str, int], asyncio.Lock] = {}


def _loop_lock(name: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    key = (name, id(loop))
    lock = _loop_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _loop_locks[key] = lock
    return lock


_client: TelegramClient | None = None

_album_client: TelegramClient | None = None

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
    return _loop_lock("import")


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
        import_stem = Path(import_session_stem()).name
        if import_sessions_share_admin_file():
            return (
                "Telegram is busy — another TBCC task is using the admin account session "
                f"({Path(_telegram_session_path()).name}.session). "
                "TBCC queues and retries automatically; try again in a few seconds. "
                "If this repeats, open TBCC-Celery for a stuck import job or restart TBCC-Celery "
                f"(poster uses {poster}.session and should not block this). "
                f"Set TBCC_IMPORT_TELEGRAM_SESSION={import_stem} and "
                "TBCC_IMPORT_AUTO_COPY_ADMIN_SESSION=1 to offload bulk imports."
            )
        return (
            "Telegram is busy — another TBCC task is using the admin account session "
            f"({Path(_telegram_session_path()).name}.session). "
            "TBCC queues and retries automatically; try again in a few seconds. "
            f"Bulk imports use {import_stem}.session and should not block dashboard thumbnails."
        )
    if "timed out" in low and "telegram admin session" in low:
        return (
            "Telegram session busy (another TBCC worker has admin.session). "
            "Retry in a few seconds, or restart TBCC-Celery if this persists."
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
    if "bound to a different event loop" in msg:
        return True
    return False


async def reset_admin_client() -> None:
    global _client
    async with _loop_lock("admin_init"):
        c = _client
        _client = None
    if c is not None:
        await graceful_telethon_disconnect(c)


async def _connect_admin_client() -> TelegramClient:
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        raise RuntimeError("Telegram API not configured")
    from app.services.telethon_session_lock import (
        assert_safe_to_open_telethon_session,
        require_telethon_session_lock,
    )
    from app.utils.telethon_session import prepare_session_sqlite_file

    assert_safe_to_open_telethon_session("admin")
    require_telethon_session_lock("admin")
    stem = _telegram_session_path()
    prepare_session_sqlite_file(stem)
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
    async with _loop_lock("admin_init"):
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
            await graceful_telethon_disconnect(old, pause_s=0.25)
        _client = await _connect_admin_client()
        return _client


async def get_telegram_storage() -> TelegramStorage:
    """Return TelegramStorage backed by a long-lived client (lazy-init)."""
    client = await _ensure_admin_client()
    return TelegramStorage(client)


async def run_telegram_io(
    fn: Callable[[TelegramStorage], Awaitable[T]],
    *,
    lock_timeout_s: float | None = None,
    max_attempts: int | None = None,
) -> T:
    """
    Run ``await fn(storage)`` under import_lock + cross-process Redis session lock.
    Retries with backoff on session/connection/SQLite lock errors (TBCC_TELEGRAM_IO_MAX_ATTEMPTS).
    """
    from app.services.telethon_session_lock import (
        acquire_admin_session_lock_async,
        release_admin_session_lock_async,
    )

    last_err: BaseException | None = None
    attempts = max_attempts if max_attempts is not None else _telegram_io_max_attempts()
    if lock_timeout_s is not None:
        attempts = min(attempts, 2)
    for attempt in range(attempts):
        lock_token = ""
        try:
            lock_token = await acquire_admin_session_lock_async(lock_timeout_s)
            async with _loop_lock("import"):
                storage = await get_telegram_storage()
                return await fn(storage)
        except Exception as e:
            last_err = e
            if "database is locked" in str(e).lower():
                try:
                    from app.services.focus_profile import record_session_stress_event

                    record_session_stress_event("admin_io")
                except Exception:
                    pass
            if attempt + 1 < attempts and _is_telethon_recoverable_error(e):
                delay = _telegram_io_backoff_seconds(attempt)
                logger.warning(
                    "Telegram admin I/O failed (attempt %s/%s): %s — reset client, retry in %.1fs",
                    attempt + 1,
                    attempts,
                    e,
                    delay,
                )
                await reset_admin_client()
                await asyncio.sleep(delay)
                continue
            raise
        finally:
            if lock_token:
                await release_admin_session_lock_async(lock_token)
            if telethon_disconnect_admin_after_io():
                try:
                    await reset_admin_client()
                except Exception:
                    logger.debug("post-I/O admin client reset failed", exc_info=True)
    if last_err is not None:
        raise last_err
    raise RuntimeError("Telegram I/O failed without exception")


def album_composer_lock_timeout_s() -> float:
    raw = (os.getenv("TBCC_ALBUM_COMPOSER_LOCK_TIMEOUT_S") or "12").strip()
    try:
        return max(3.0, min(30.0, float(raw)))
    except ValueError:
        return 12.0


async def run_telegram_io_interactive(fn: Callable[[TelegramStorage], Awaitable[T]]) -> T:
    """Album Composer / interactive sends — dedicated session, no Celery lock wait."""
    return await run_telegram_album_composer_io(fn)


def _try_bootstrap_album_from_admin() -> bool:
    """Copy admin.session -> admin_album.session (opt-in via TBCC_ALBUM_COMPOSER_AUTO_COPY_ADMIN_SESSION)."""
    flag = os.getenv("TBCC_ALBUM_COMPOSER_AUTO_COPY_ADMIN_SESSION", "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return False
    admin_stem = admin_session_stem()
    album_stem = album_composer_session_stem()
    if os.path.normcase(os.path.normpath(admin_stem)) == os.path.normcase(os.path.normpath(album_stem)):
        return False
    admin_path = admin_stem + ".session"
    album_path = album_stem + ".session"
    if not os.path.isfile(admin_path):
        logger.warning(
            "TBCC_ALBUM_COMPOSER_AUTO_COPY_ADMIN_SESSION is set but admin.session not found (%s)",
            admin_path,
        )
        return False
    try:
        import sqlite3

        src = sqlite3.connect(admin_path)
        dst = sqlite3.connect(album_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        logger.info(
            "Bootstrapped album composer Telethon session from %s -> %s",
            admin_path,
            album_path,
        )
        return True
    except Exception:
        logger.exception("Failed to bootstrap album composer session from admin.session")
        return False


async def reset_album_client() -> None:
    global _album_client
    async with _loop_lock("album_init"):
        c = _album_client
        _album_client = None
    if c is not None:
        await graceful_telethon_disconnect(c)


async def _connect_album_client() -> TelegramClient:
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        raise RuntimeError("Telegram API not configured")
    from app.services.telethon_session_lock import assert_safe_to_open_telethon_session
    from app.utils.telethon_session import prepare_session_sqlite_file

    assert_safe_to_open_telethon_session("album")
    stem = album_composer_session_stem()
    album_path = stem + ".session"
    if not os.path.isfile(album_path):
        _try_bootstrap_album_from_admin()
    prepare_session_sqlite_file(stem)
    client = TelegramClient(stem, int(os.environ["API_ID"]), os.environ["API_HASH"])
    await client.connect()
    configure_telethon_sqlite_session(client)
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError(
            f"Telegram album composer session is not logged in ({Path(stem).name}.session). "
            "Set TBCC_ALBUM_COMPOSER_AUTO_COPY_ADMIN_SESSION=1 and restart, or run login_telethon_sessions.py"
        )
    return client


async def _ensure_album_client() -> TelegramClient:
    global _album_client
    async with _loop_lock("album_init"):
        if _album_client is not None and _album_client.is_connected():
            return _album_client
        if _album_client is not None:
            try:
                await _album_client.connect()
                configure_telethon_sqlite_session(_album_client)
                if await _album_client.is_user_authorized():
                    return _album_client
            except Exception:
                logger.warning("album composer reconnect failed; resetting session client", exc_info=True)
            old = _album_client
            _album_client = None
            await graceful_telethon_disconnect(old, pause_s=0.25)
        _album_client = await _connect_album_client()
        return _album_client


async def get_album_telegram_storage() -> TelegramStorage:
    client = await _ensure_album_client()
    return TelegramStorage(client)


async def run_telegram_album_composer_io(
    fn: Callable[[TelegramStorage], Awaitable[T]],
    *,
    max_attempts: int = 3,
) -> T:
    """
    Album Composer hot path — uses admin_album.session (separate SQLite file).
    Does NOT wait on tbcc:lock:admin_telegram_session (Celery import queue).
    Still serializes MTProto via tbcc:lock:telegram_account_mtproto when enabled.
    """
    from app.services.telethon_session_lock import (
        acquire_telegram_account_lock_async,
        release_telegram_account_lock_async,
        telegram_account_lock_enabled,
    )

    last_err: BaseException | None = None
    for attempt in range(max_attempts):
        account_token = ""
        try:
            if telegram_account_lock_enabled():
                account_token = await acquire_telegram_account_lock_async(
                    album_composer_lock_timeout_s()
                )
            async with _loop_lock("album_import"):
                storage = await get_album_telegram_storage()
                return await fn(storage)
        except Exception as e:
            last_err = e
            if attempt + 1 < max_attempts and _is_telethon_recoverable_error(e):
                delay = _telegram_io_backoff_seconds(attempt)
                logger.warning(
                    "Album composer Telethon I/O failed (attempt %s/%s): %s — retry in %.1fs",
                    attempt + 1,
                    max_attempts,
                    e,
                    delay,
                )
                await reset_album_client()
                await asyncio.sleep(delay)
                continue
            raise
        finally:
            if account_token:
                await release_telegram_account_lock_async(account_token)
    if last_err is not None:
        raise last_err
    raise RuntimeError("Album composer Telegram I/O failed without exception")


_import_client: TelegramClient | None = None


def _try_bootstrap_import_from_admin() -> bool:
    """Copy admin.session -> admin_import.session (opt-in via TBCC_IMPORT_AUTO_COPY_ADMIN_SESSION)."""
    flag = os.getenv("TBCC_IMPORT_AUTO_COPY_ADMIN_SESSION", "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return False
    admin_stem = admin_session_stem()
    import_stem = import_session_stem()
    if os.path.normcase(os.path.normpath(admin_stem)) == os.path.normcase(os.path.normpath(import_stem)):
        return False
    admin_path = admin_stem + ".session"
    import_path = import_stem + ".session"
    if not os.path.isfile(admin_path):
        logger.warning(
            "TBCC_IMPORT_AUTO_COPY_ADMIN_SESSION is set but admin.session not found (%s)",
            admin_path,
        )
        return False
    try:
        import sqlite3

        src = sqlite3.connect(admin_path)
        dst = sqlite3.connect(import_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        logger.info(
            "Bootstrapped import Telethon session from %s -> %s",
            admin_path,
            import_path,
        )
        return True
    except Exception:
        logger.exception("Failed to bootstrap import session from admin.session")
        return False


async def reset_import_client() -> None:
    global _import_client
    async with _loop_lock("import_init"):
        c = _import_client
        _import_client = None
    if c is not None:
        await graceful_telethon_disconnect(c)


async def _connect_import_client() -> TelegramClient:
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        raise RuntimeError("Telegram API not configured")
    from app.services.telethon_session_lock import (
        assert_safe_to_open_telethon_session,
        require_telethon_session_lock,
    )
    from app.utils.telethon_session import prepare_session_sqlite_file

    assert_safe_to_open_telethon_session("import")
    require_telethon_session_lock("import")
    stem = import_session_stem()
    import_path = stem + ".session"
    if not os.path.isfile(import_path):
        _try_bootstrap_import_from_admin()
    prepare_session_sqlite_file(stem)
    client = TelegramClient(stem, int(os.environ["API_ID"]), os.environ["API_HASH"])
    await client.connect()
    configure_telethon_sqlite_session(client)
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError(
            f"Telegram import session is not logged in ({Path(stem).name}.session). "
            "Set TBCC_IMPORT_AUTO_COPY_ADMIN_SESSION=1 and restart, or run login_telethon_sessions.py"
        )
    return client


async def _ensure_import_client() -> TelegramClient:
    global _import_client
    async with _loop_lock("import_init"):
        if _import_client is not None and _import_client.is_connected():
            return _import_client
        if _import_client is not None:
            try:
                await _import_client.connect()
                configure_telethon_sqlite_session(_import_client)
                if await _import_client.is_user_authorized():
                    return _import_client
            except Exception:
                logger.warning("import session reconnect failed; resetting session client", exc_info=True)
            old = _import_client
            _import_client = None
            await graceful_telethon_disconnect(old, pause_s=0.25)
        _import_client = await _connect_import_client()
        return _import_client


async def get_import_telegram_storage() -> TelegramStorage:
    client = await _ensure_import_client()
    return TelegramStorage(client)


async def run_telegram_import_io(
    fn: Callable[[TelegramStorage], Awaitable[T]],
    *,
    lock_timeout_s: float | None = None,
    max_attempts: int | None = None,
) -> T:
    """
    Bulk import hot path — uses admin_import.session when configured separately from admin.
    Falls back to run_telegram_io when import shares admin.session.
    Uses its own Redis lock so Celery imports do not block dashboard thumbnails.
    """
    if import_sessions_share_admin_file():
        return await run_telegram_io(fn, lock_timeout_s=lock_timeout_s, max_attempts=max_attempts)

    from app.services.telethon_session_lock import (
        acquire_import_session_lock_async,
        release_import_session_lock_async,
    )

    last_err: BaseException | None = None
    attempts = max_attempts if max_attempts is not None else _telegram_io_max_attempts()
    if lock_timeout_s is not None:
        attempts = min(attempts, 2)
    for attempt in range(attempts):
        lock_token = ""
        try:
            lock_token = await acquire_import_session_lock_async(lock_timeout_s)
            async with _loop_lock("import_work"):
                storage = await get_import_telegram_storage()
                return await fn(storage)
        except Exception as e:
            last_err = e
            if "database is locked" in str(e).lower():
                try:
                    from app.services.focus_profile import record_session_stress_event

                    record_session_stress_event("import_io")
                except Exception:
                    pass
            if attempt + 1 < attempts and _is_telethon_recoverable_error(e):
                delay = _telegram_io_backoff_seconds(attempt)
                logger.warning(
                    "Telegram import I/O failed (attempt %s/%s): %s — reset client, retry in %.1fs",
                    attempt + 1,
                    attempts,
                    e,
                    delay,
                )
                await reset_import_client()
                await asyncio.sleep(delay)
                continue
            raise
        finally:
            if lock_token:
                await release_import_session_lock_async(lock_token)
            if telethon_disconnect_import_after_io():
                try:
                    await reset_import_client()
                except Exception:
                    logger.debug("post-I/O import client reset failed", exc_info=True)
    if last_err is not None:
        raise last_err
    raise RuntimeError("Telegram import I/O failed without exception")


async def run_telegram_client_io(fn: Callable[[TelegramClient], Awaitable[T]]) -> T:
    """Same retry/lock semantics as run_telegram_io but for raw Telethon client callbacks."""
    from app.services.telethon_session_lock import (
        acquire_admin_session_lock_async,
        release_admin_session_lock_async,
    )

    last_err: BaseException | None = None
    max_attempts = _telegram_io_max_attempts()
    for attempt in range(max_attempts):
        lock_token = ""
        try:
            lock_token = await acquire_admin_session_lock_async()
            async with _loop_lock("import"):
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
        finally:
            if lock_token:
                await release_admin_session_lock_async(lock_token)
            if telethon_disconnect_admin_after_io():
                try:
                    await reset_admin_client()
                except Exception:
                    logger.debug("post-I/O admin client reset failed", exc_info=True)
    if last_err is not None:
        raise last_err
    raise RuntimeError("Telegram client I/O failed without exception")


async def check_import_telegram_session() -> dict:
    """Probe the import Telethon session (Saved Messages / context-menu sends)."""
    try:
        storage = await get_import_telegram_storage()
        me = await storage.client.get_me()
        username = getattr(me, "username", None) or ""
        return {
            "ok": True,
            "user_id": me.id,
            "username": username,
            "session": Path(import_session_stem()).name,
            "import_shares_admin_file": import_sessions_share_admin_file(),
        }
    except Exception as e:
        return {"ok": False, "error": friendly_telegram_error(e)}


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
            "import_session": Path(import_session_stem()).name,
            "sessions_share_file": telethon_sessions_share_file(),
            "import_shares_admin_file": import_sessions_share_admin_file(),
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
