"""Stable Telethon session file paths (backend root, not process cwd)."""
from __future__ import annotations

import os
from pathlib import Path


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
