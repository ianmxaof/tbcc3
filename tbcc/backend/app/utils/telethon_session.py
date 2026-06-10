"""Stable Telethon session file paths (backend root, not process cwd)."""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _backend_root() -> Path:
    # app/utils/telethon_session.py -> parents[2] == backend package root (tbcc/backend)
    return Path(__file__).resolve().parents[2]


def normalize_session_stem(configured: str) -> str:
    """Telethon first arg is path stem; strip accidental .session suffix."""
    s = configured.strip().strip('"')
    if s.lower().endswith(".session"):
        return s[: -len(".session")]
    return s


def admin_session_stem() -> str:
    """Admin / import / channel-access session (TELEGRAM_SESSION_PATH or tbcc/backend/admin)."""
    configured = (os.environ.get("TELEGRAM_SESSION_PATH") or "").strip()
    if not configured:
        return str(_backend_root() / "admin")
    s = normalize_session_stem(configured)
    p = Path(s)
    if p.is_absolute():
        return str(p)
    return str((_backend_root() / p).resolve())


def poster_session_stem() -> str:
    """Poster worker session (TBCC_POSTER_TELEGRAM_SESSION basename or tbcc/backend/admin_poster)."""
    raw = (os.getenv("TBCC_POSTER_TELEGRAM_SESSION") or "admin_poster").strip() or "admin_poster"
    p = Path(raw)
    if p.is_absolute():
        return normalize_session_stem(str(p))
    if "/" in raw or "\\" in raw:
        return normalize_session_stem(str((_backend_root() / raw).resolve()))
    return str(_backend_root() / raw)


def album_composer_session_stem() -> str:
    """Dedicated Telethon session for Album Composer (avoids admin.session Redis lock)."""
    raw = (os.getenv("TBCC_ALBUM_COMPOSER_TELEGRAM_SESSION") or "admin_album").strip() or "admin_album"
    p = Path(raw)
    if p.is_absolute():
        return normalize_session_stem(str(p))
    if "/" in raw or "\\" in raw:
        return normalize_session_stem(str((_backend_root() / raw).resolve()))
    return str(_backend_root() / raw)


def import_session_stem() -> str:
    """Bulk import / Saved Messages / channel scan session (separate from dashboard admin.session)."""
    raw = (os.getenv("TBCC_IMPORT_TELEGRAM_SESSION") or "admin_import").strip() or "admin_import"
    p = Path(raw)
    if p.is_absolute():
        return normalize_session_stem(str(p))
    if "/" in raw or "\\" in raw:
        return normalize_session_stem(str((_backend_root() / raw).resolve()))
    return str(_backend_root() / raw)


def _session_paths_equal(a_stem: str, b_stem: str) -> bool:
    return os.path.normcase(os.path.normpath(a_stem + ".session")) == os.path.normcase(
        os.path.normpath(b_stem + ".session")
    )


def telethon_sessions_share_file() -> bool:
    """True when admin + poster workers would contend on the same SQLite session file."""
    return _session_paths_equal(admin_session_stem(), poster_session_stem())


def import_sessions_share_admin_file() -> bool:
    """True when imports still use admin.session (no dedicated import file configured)."""
    return _session_paths_equal(admin_session_stem(), import_session_stem())


def sqlite_busy_timeout_ms() -> int:
    raw = (os.getenv("TBCC_TELEGRAM_SQLITE_BUSY_TIMEOUT_MS") or "120000").strip()
    try:
        return max(1000, min(600_000, int(raw)))
    except ValueError:
        return 120_000


def configure_telethon_sqlite_session(client) -> None:
    """WAL + long busy_timeout on Telethon's SQLite session (reduces 'database is locked')."""
    try:
        conn = getattr(client.session, "_conn", None)
        if conn is None:
            return
        ms = sqlite_busy_timeout_ms()
        conn.execute(f"PRAGMA busy_timeout={ms}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        logger.debug("could not configure Telethon session SQLite pragmas", exc_info=True)


def _env_truthy(name: str) -> bool | None:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return None
    return raw not in ("0", "false", "no", "off")


def telethon_disconnect_admin_after_io() -> bool:
    """
    When True, disconnect the admin Telethon client after each serialized I/O op.
    Default False when poster + import use separate session files (recommended .env);
    True when they share admin.session so Celery/API do not hold SQLite locks.
    """
    override = _env_truthy("TBCC_TELEGRAM_DISCONNECT_AFTER_IO")
    if override is not None:
        return override
    return telethon_sessions_share_file() or import_sessions_share_admin_file()


def telethon_disconnect_import_after_io() -> bool:
    """Same as admin, but for the dedicated import session client."""
    override = _env_truthy("TBCC_IMPORT_TELEGRAM_DISCONNECT_AFTER_IO")
    if override is not None:
        return override
    override_global = _env_truthy("TBCC_TELEGRAM_DISCONNECT_AFTER_IO")
    if override_global is not None:
        return override_global
    return import_sessions_share_admin_file()


async def graceful_telethon_disconnect(client, *, pause_s: float = 0.5) -> None:
    """
    Disconnect Telethon without leaving send/recv tasks on a closing asyncio loop.
    Celery uses asyncio.run() per task — reusing or half-closing clients causes
    'Event loop is closed' / 'Task was destroyed but it is pending' noise.
    """
    import asyncio

    if client is None:
        return
    try:
        connected = False
        try:
            connected = bool(client.is_connected())
        except Exception:
            connected = False
        if connected:
            await asyncio.sleep(0)
            await client.disconnect()
    except RuntimeError as e:
        if "event loop is closed" not in str(e).lower():
            logger.debug("telethon disconnect runtime error", exc_info=True)
    except GeneratorExit:
        pass
    except Exception:
        logger.debug("telethon disconnect failed", exc_info=True)
    if pause_s > 0:
        await asyncio.sleep(pause_s)
