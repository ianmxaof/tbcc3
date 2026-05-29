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


def telethon_sessions_share_file() -> bool:
    """True when admin + poster workers would contend on the same SQLite session file."""
    return os.path.normcase(
        os.path.normpath(admin_session_stem() + ".session")
    ) == os.path.normcase(os.path.normpath(poster_session_stem() + ".session"))


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


async def graceful_telethon_disconnect(client, *, pause_s: float = 0.35) -> None:
    """
    Disconnect Telethon without leaving send/recv tasks on a closing asyncio loop.
    Celery uses asyncio.run() per task — reusing or half-closing clients causes
    'Event loop is closed' / 'Task was destroyed but it is pending' noise.
    """
    import asyncio

    if client is None:
        return
    try:
        if getattr(client, "is_connected", lambda: False)():
            await client.disconnect()
    except RuntimeError as e:
        if "event loop is closed" not in str(e).lower():
            logger.debug("telethon disconnect runtime error", exc_info=True)
    except Exception:
        logger.debug("telethon disconnect failed", exc_info=True)
    if pause_s > 0:
        await asyncio.sleep(pause_s)
