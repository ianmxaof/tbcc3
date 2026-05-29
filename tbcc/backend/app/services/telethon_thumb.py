"""Throttled Telegram reads for dashboard thumbnails (avoids SQLite session lock storms)."""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import HTTPException

from app.api.media import MediaFetchContext

logger = logging.getLogger(__name__)

_THUMB_SEM: asyncio.Semaphore | None = None

# Sentinel: this media genuinely has no usable preview (e.g. a video with no poster frame).
# Distinct from None (a transient busy/lock/timeout that should be retried on next reload),
# so the caller can negative-cache it for hours instead of re-asking Telegram every load.
NO_PREVIEW = object()


def _thumb_concurrency() -> int:
    raw = (os.getenv("TBCC_THUMBNAIL_FETCH_CONCURRENCY") or "2").strip()
    try:
        return max(1, min(8, int(raw)))
    except ValueError:
        return 2


def _thumb_timeout_s() -> float:
    raw = (os.getenv("TBCC_THUMBNAIL_FETCH_TIMEOUT_S") or "45").strip()
    try:
        return max(5.0, min(120.0, float(raw)))
    except ValueError:
        return 45.0


def _get_thumb_semaphore() -> asyncio.Semaphore:
    global _THUMB_SEM
    if _THUMB_SEM is None:
        _THUMB_SEM = asyncio.Semaphore(_thumb_concurrency())
    return _THUMB_SEM


async def fetch_thumbnail_bytes(ctx: MediaFetchContext):
    """
    Download preview bytes with bounded concurrency and timeout.

    Returns:
      (data, mime)  on success
      NO_PREVIEW    when the media has no usable preview (caller negative-caches it)
      None          on a transient busy / lock / timeout (caller should retry later)
    """
    from app.api.media import _fetch_media_bytes_and_type, _fetch_saved_message_thumbnail_bytes

    sem = _get_thumb_semaphore()
    timeout_s = _thumb_timeout_s()

    async def _do_fetch():
        mt = (ctx.media_type or "").lower()
        if mt == "video":
            # Grid preview only: use Telegram's poster frame. NEVER download the full
            # video here — that pulls megabytes through the serialized admin session and
            # is the slow path that starved the dashboard. No poster → NO_PREVIEW (so it
            # is negative-cached, not retried); full bytes stay in the lightbox via /file.
            thumb = await _fetch_saved_message_thumbnail_bytes(ctx)
            return thumb if thumb is not None else NO_PREVIEW
        return await _fetch_media_bytes_and_type(ctx)

    try:
        async with sem:
            return await asyncio.wait_for(_do_fetch(), timeout=timeout_s)
    except asyncio.TimeoutError:
        logger.warning("thumbnail fetch timed out media_id=%s after %.0fs", ctx.id, timeout_s)
        return None
    except HTTPException:
        raise
    except Exception as e:
        msg = str(e).lower()
        if "database is locked" in msg or "sqlite_busy" in msg:
            logger.warning("thumbnail fetch sqlite locked media_id=%s", ctx.id)
        else:
            logger.warning("thumbnail fetch failed media_id=%s: %s", ctx.id, e)
        return None
