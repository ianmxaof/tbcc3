"""
Pool imports from the extension/dashboard — store bytes on disk, no Saved Messages upload.

Saved Messages path (saved_only=true) is unchanged. Pool path (saved_only=false) writes here
so imports do not contend on the Telethon import session or clutter Saved Messages.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.media import Media
from app.services.media_sniff import sniff_media_kind, telegram_media_type_from_sniff
from app.services.media_watermark import maybe_apply_media_watermark

logger = logging.getLogger(__name__)

# telegram_message_id=0 marks rows whose bytes live on disk (not in Saved Messages).
LOCAL_TELEGRAM_MESSAGE_ID = 0


def pool_import_local_enabled() -> bool:
    return (os.getenv("TBCC_POOL_IMPORT_LOCAL") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def media_files_root() -> Path:
    env = (os.getenv("TBCC_MEDIA_FILES_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    tbcc = here.parent.parent.parent.parent
    return (tbcc / "uploads" / "media-files").resolve()


def ensure_media_files_dir() -> Path:
    root = media_files_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def content_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def local_file_unique_id(digest: str) -> str:
    return f"local:{digest}"


def local_file_id(digest: str, ext: str) -> str:
    return f"local:{digest[:32]}.{ext}"


def is_local_pool_media(media: Media) -> bool:
    """telegram_message_id=0 marks on-disk pool imports (not Saved Messages)."""
    try:
        raw = getattr(media, "telegram_message_id", None)
        if raw is None:
            return False
        return int(raw) == LOCAL_TELEGRAM_MESSAGE_ID
    except (TypeError, ValueError):
        return False


def local_media_path(media: Media) -> Path | None:
    fid = str(getattr(media, "file_id", "") or "").strip()
    if not fid.startswith("local:"):
        return None
    name = fid.split("local:", 1)[-1].strip()
    if not name or "/" in name or "\\" in name:
        return None
    p = ensure_media_files_dir() / name
    return p if p.is_file() else None


def telethon_file_from_media(media: Media):
    """BytesIO with .name set — for poster send_file uploads."""
    import io

    data = read_local_media_bytes(media)
    if not data:
        return None
    _, ext = _ext_for_bytes(data, str(getattr(media, "media_type", "") or "photo"))
    f = io.BytesIO(data)
    f.name = f"media.{ext}"
    return f


def read_local_media_bytes(media: Media) -> bytes | None:
    p = local_media_path(media)
    if p:
        try:
            return p.read_bytes()
        except OSError:
            logger.debug("read local media failed id=%s path=%s", getattr(media, "id", "?"), p, exc_info=True)
    # Fallback: dashboard thumb cache (full file missing or moved).
    try:
        from app.services.media_cache_storage import cached_thumb_path

        mid = int(getattr(media, "id", 0) or 0)
        if mid > 0:
            tp = cached_thumb_path(mid)
            if tp:
                logger.warning(
                    "Using thumb cache for media id=%s (full file missing at %s)",
                    mid,
                    p,
                )
                return tp.read_bytes()
    except Exception:
        logger.debug("thumb fallback failed media_id=%s", getattr(media, "id", "?"), exc_info=True)
    return None


def _ext_for_bytes(data: bytes, media_type_hint: str) -> tuple[str, str]:
    kind, ext = sniff_media_kind(data)
    hint = (media_type_hint or "photo").lower()
    if hint not in ("photo", "video", "document"):
        hint = "photo"
    if kind != "document":
        media_type = telegram_media_type_from_sniff(kind)
    else:
        media_type = hint
    if ext == "bin":
        ext = "jpg" if media_type == "photo" else "mp4" if media_type == "video" else "dat"
    return media_type, ext


def _maybe_write_thumb_cache(media_id: int, data: bytes, media_type: str) -> None:
    if (media_type or "").lower() not in ("photo", "gif"):
        return
    try:
        from app.api.media import _image_bytes_to_thumbnail_jpeg
        from app.services.media_cache_storage import write_thumb_atomic

        jpeg = _image_bytes_to_thumbnail_jpeg(data)
        if jpeg:
            write_thumb_atomic(media_id, jpeg)
    except Exception:
        logger.debug("local import thumb cache skipped media_id=%s", media_id, exc_info=True)


def store_pool_media_from_bytes(
    data: bytes,
    media_type_hint: str,
    source: str,
    pool_id: int,
    db: Session,
    *,
    skip_watermark: bool = False,
) -> Media | None:
    """Write bytes to disk and create a pending Media row (no Telegram I/O)."""
    if not data:
        return None
    if not skip_watermark:
        data = maybe_apply_media_watermark(data, media_type_hint)
    media_type, ext = _ext_for_bytes(data, media_type_hint)
    digest = content_digest(data)
    unique = local_file_unique_id(digest)
    existing = (
        db.query(Media)
        .filter(Media.file_unique_id == unique, Media.pool_id == pool_id)
        .first()
    )
    if existing:
        return None

    root = ensure_media_files_dir()
    rel_name = f"{digest[:32]}.{ext}"
    path = root / rel_name
    if not path.is_file():
        tmp = root / f".{digest[:16]}.{os.getpid()}.tmp"
        try:
            tmp.write_bytes(data)
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    record = Media(
        telegram_message_id=LOCAL_TELEGRAM_MESSAGE_ID,
        file_id=local_file_id(digest, ext),
        file_unique_id=unique,
        media_type=media_type,
        source_channel=(source or "import:local")[:512],
        pool_id=pool_id,
        status="pending",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    _maybe_write_thumb_cache(int(record.id), data, media_type)
    try:
        from app.services.media_tagging import apply_auto_tags_for_new_media

        apply_auto_tags_for_new_media(db, record.id)
        from app.services.auto_tag_enrich import enqueue_auto_tag_enrich_if_enabled

        enqueue_auto_tag_enrich_if_enabled(record.id)
    except Exception:
        logger.exception("auto-tag failed for local media id=%s", record.id)
    return record
