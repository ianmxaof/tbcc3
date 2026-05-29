"""
Persistent on-disk thumbnail cache for the dashboard Media Library.

Why this exists: every dashboard grid render previously re-downloaded each thumbnail
from Telegram through the single serialized admin session (``_import_lock`` in
``telegram_admin.run_telegram_io``). A 100-item gallery fired 100 downloads that
queued one-at-a-time behind that lock and starved unrelated endpoints (``/pools``,
bulk approve), producing the dashboard's "Could not load pools / request timed out".

With this cache a thumbnail is downloaded from Telegram exactly once, written to disk
as a small JPEG, and every later request is served as a static file — no DB query, no
Telegram session, no SQLite connection. That keeps the gallery solid no matter what
else (imports, sends, scraping, bulk approve) is running.

Cache entries (keyed by media id only — see ``clear_cached_thumb`` for invalidation):
  ``<id>.jpg``   downscaled JPEG preview (image or video poster frame)
  ``<id>.none``  negative marker: this media has no usable preview. Avoids re-hitting
                 Telegram on every reload for posterless videos / failed fetches.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Negative markers expire so a transient failure (session busy) self-heals on a later view.
NEGATIVE_TTL_SECONDS = 6 * 60 * 60  # 6h


def media_cache_root() -> Path:
    env = (os.getenv("TBCC_MEDIA_CACHE_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    tbcc = here.parent.parent.parent.parent  # .../tbcc
    return (tbcc / "uploads" / "media-cache" / "thumbs").resolve()


def ensure_media_cache_dir() -> Path:
    root = media_cache_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _thumb_path(media_id: int) -> Path:
    return ensure_media_cache_dir() / f"{int(media_id)}.jpg"


def _negative_path(media_id: int) -> Path:
    return ensure_media_cache_dir() / f"{int(media_id)}.none"


def cached_thumb_path(media_id: int) -> Path | None:
    """Return the cached JPEG path if a non-empty file exists, else None."""
    p = _thumb_path(media_id)
    try:
        if p.is_file() and p.stat().st_size > 0:
            return p
    except OSError:
        return None
    return None


def negative_marker_fresh(media_id: int) -> bool:
    """True if we recently determined this media has no usable preview (skip Telegram)."""
    p = _negative_path(media_id)
    try:
        if not p.is_file():
            return False
        age = time.time() - p.stat().st_mtime
        if age <= NEGATIVE_TTL_SECONDS:
            return True
        # Stale — drop it so the next view retries the fetch.
        p.unlink(missing_ok=True)
        return False
    except OSError:
        return False


def write_thumb_atomic(media_id: int, data: bytes) -> Path:
    """Write JPEG bytes via temp + rename so concurrent misses never serve a half-written file."""
    root = ensure_media_cache_dir()
    final = root / f"{int(media_id)}.jpg"
    tmp = root / f"{int(media_id)}.{os.getpid()}.{time.time_ns()}.tmp"
    try:
        tmp.write_bytes(data)
        os.replace(tmp, final)  # atomic on same filesystem
        # A fresh real thumbnail supersedes any stale negative marker.
        _negative_path(media_id).unlink(missing_ok=True)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return final


def write_negative_marker(media_id: int) -> None:
    try:
        _negative_path(media_id).write_bytes(b"")
    except OSError:
        logger.debug("could not write negative thumb marker for media_id=%s", media_id, exc_info=True)


def clear_cached_thumb(media_id: int) -> None:
    """Drop cached JPEG + negative marker (on delete, or ?refresh=1)."""
    _thumb_path(media_id).unlink(missing_ok=True)
    _negative_path(media_id).unlink(missing_ok=True)
