"""
Dashboard thumbnail cache — write at import, warm on Celery (import session).

The API serves thumbnails from disk only. Telegram downloads happen on the telegram
Celery queue via admin_import.session so dashboard browsing never contends with
admin.session used by sends / scrapers / enrich.
"""

from __future__ import annotations

import io
import logging
import os
from typing import Literal

from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto

logger = logging.getLogger(__name__)

WarmResult = Literal["cached", "warmed", "no_preview", "missing", "failed"]


def bytes_to_thumbnail_jpeg(data: bytes, max_edge: int = 320) -> bytes | None:
    """Downscale image bytes to a small JPEG for grid previews."""
    try:
        from PIL import Image, ImageOps

        im = Image.open(io.BytesIO(data))
        im.seek(0)
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "P", "L") or im.mode != "RGB":
            im = im.convert("RGB")
        w, h = im.size
        if w < 1 or h < 1:
            return None
        if max(w, h) > max_edge:
            ratio = max_edge / float(max(w, h))
            im = im.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=82, optimize=True)
        return out.getvalue()
    except Exception:
        logger.debug("thumbnail JPEG resize skipped", exc_info=True)
        return None


def api_thumbnail_telegram_enabled() -> bool:
    """When false (default), GET /thumbnail never blocks on Telethon — Celery warms instead."""
    return (os.getenv("TBCC_THUMBNAIL_API_TELEGRAM") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def queue_thumbnail_warm(media_ids: list[int]) -> dict:
    """Enqueue uncached ids on the telegram worker; return counts without blocking."""
    from app.services.media_cache_storage import cached_thumb_path, negative_marker_fresh

    need: list[int] = []
    already = 0
    for raw in media_ids:
        try:
            mid = int(raw)
        except (TypeError, ValueError):
            continue
        if mid <= 0:
            continue
        if cached_thumb_path(mid) or negative_marker_fresh(mid):
            already += 1
        elif mid not in need:
            need.append(mid)
    if need:
        from app.services.post_scheduler import (
            posting_stalled_for_admission,
            thumbnail_warm_pause_when_post_stalled,
        )
        from app.workers.thumbnail_warm_worker import warm_media_thumbnails

        if thumbnail_warm_pause_when_post_stalled() and posting_stalled_for_admission():
            return {"queued": 0, "already_cached": already, "paused": True}
        if thumbnail_warm_pause_when_imports_pending() and _open_import_jobs_above_threshold():
            return {"queued": 0, "already_cached": already, "paused": True, "reason": "imports_pending"}
        warm_media_thumbnails.delay(need[:60])
    return {"queued": len(need[:60]), "already_cached": already}


def thumbnail_warm_pause_when_imports_pending() -> bool:
    """Defer thumbnail warms while storage-hub / channel imports need the telegram queue."""
    return (os.getenv("TBCC_THUMBNAIL_WARM_PAUSE_WHEN_IMPORTS") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _import_priority_threshold() -> int:
    raw = (os.getenv("TBCC_WATCHDOG_IMPORT_PRIORITY_THRESHOLD") or "3").strip()
    try:
        return max(1, min(50, int(raw)))
    except ValueError:
        return 3


def _open_import_jobs_above_threshold() -> bool:
    try:
        from app.database.session import SessionLocal
        from app.models.import_job import ImportJob
        from app.services.import_pipeline import TERMINAL_STATUSES

        db = SessionLocal()
        try:
            n = int(
                db.query(ImportJob)
                .filter(~ImportJob.status.in_(list(TERMINAL_STATUSES)))
                .count()
            )
        finally:
            db.close()
        return n >= _import_priority_threshold()
    except Exception:
        return False


async def cache_thumb_from_message(client, message, media_id: int) -> bool:
    """
    Best-effort preview write while the import client already holds the message.
    Called from TelegramStorage._index_message right after a pool row is created.
    """
    from app.services.media_cache_storage import (
        cached_thumb_path,
        write_negative_marker,
        write_thumb_atomic,
    )

    mid = int(media_id)
    if cached_thumb_path(mid):
        return True
    if not message or not getattr(message, "media", None):
        return False
    try:
        data = await _download_preview_bytes(client, message)
        if not data:
            write_negative_marker(mid)
            return False
        jpeg = bytes_to_thumbnail_jpeg(data)
        if not jpeg:
            write_negative_marker(mid)
            return False
        write_thumb_atomic(mid, jpeg)
        return True
    except Exception:
        logger.debug("ingest thumb cache skipped media_id=%s", mid, exc_info=True)
        return False


async def _download_preview_bytes(client, message) -> bytes | None:
    buf = io.BytesIO()
    await client.download_media(message, file=buf, thumb=-1)
    data = buf.getvalue()
    if data:
        return data
    if isinstance(message.media, MessageMediaPhoto):
        buf = io.BytesIO()
        await client.download_media(message, file=buf)
        return buf.getvalue() or None
    if isinstance(message.media, MessageMediaDocument):
        mime = (message.media.document.mime_type or "").lower()
        if "image" in mime or mime in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            buf = io.BytesIO()
            await client.download_media(message, file=buf)
            return buf.getvalue() or None
    return None


async def warm_thumbnail_for_media(storage, media) -> WarmResult:
    """Download one preview via import session and persist to disk cache."""
    from app.services.local_media_storage import LOCAL_TELEGRAM_MESSAGE_ID, local_media_path
    from app.services.media_cache_storage import (
        cached_thumb_path,
        negative_marker_fresh,
        write_negative_marker,
        write_thumb_atomic,
    )

    mid = int(media.id)
    if cached_thumb_path(mid):
        return "cached"
    if negative_marker_fresh(mid):
        return "no_preview"

    try:
        if media.telegram_message_id == LOCAL_TELEGRAM_MESSAGE_ID:
            path = local_media_path(media)
            if not path or not path.is_file():
                return "missing"
            data = path.read_bytes()
            mt = (media.media_type or "").lower()
            if mt == "video":
                from app.services.media_frame_sample import extract_video_frame_jpeg

                frame = extract_video_frame_jpeg(data)
                if not frame:
                    write_negative_marker(mid)
                    return "no_preview"
                write_thumb_atomic(mid, frame)
                return "warmed"
            jpeg = bytes_to_thumbnail_jpeg(data)
            if not jpeg:
                write_negative_marker(mid)
                return "no_preview"
            write_thumb_atomic(mid, jpeg)
            return "warmed"

        msg_id = media.telegram_message_id
        if msg_id is None:
            return "missing"

        client = storage.client
        messages = await client.get_messages("me", ids=int(msg_id))
        msg = messages[0] if isinstance(messages, (list, tuple)) and messages else messages
        if not msg or not msg.media:
            return "missing"
        data = await _download_preview_bytes(client, msg)
        if not data:
            write_negative_marker(mid)
            return "no_preview"
        jpeg = bytes_to_thumbnail_jpeg(data)
        if not jpeg:
            write_negative_marker(mid)
            return "no_preview"
        write_thumb_atomic(mid, jpeg)
        return "warmed"
    except Exception:
        logger.warning("warm thumbnail failed media_id=%s", mid, exc_info=True)
        return "failed"


async def run_warm_thumbnails_async(media_ids: list[int]) -> dict:
    from app.database.session import SessionLocal
    from app.models.media import Media
    from app.services.telegram_admin import run_telegram_import_io

    counts = {"warmed": 0, "cached": 0, "no_preview": 0, "missing": 0, "failed": 0}

    async def _job(storage):
        db = SessionLocal()
        try:
            for raw in media_ids:
                try:
                    mid = int(raw)
                except (TypeError, ValueError):
                    continue
                if mid <= 0:
                    continue
                row = db.query(Media).filter(Media.id == mid).first()
                if not row:
                    counts["missing"] += 1
                    continue
                result = await warm_thumbnail_for_media(storage, row)
                counts[result] = counts.get(result, 0) + 1
        finally:
            db.close()

    await run_telegram_import_io(_job)
    return counts
