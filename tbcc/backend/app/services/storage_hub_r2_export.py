"""Export Storage Hub / trusted AOF pool media to Cloudflare R2 (aof-media).

Bytes are pulled with Telethon on the island (telegram queue), uploaded once via
``upload_bytes_to_r2``, and the key is stored under ``classification_json.r2``.
aof-forum then indexes ``object_key`` without re-downloading through Cloudflare.
"""

from __future__ import annotations

import json
import logging
import mimetypes
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

R2_JSON_KEY = "r2"
OBJECT_KEY_PREFIX = "library/hub"


def r2_meta_from_media(media) -> dict[str, Any] | None:
    raw = getattr(media, "classification_json", None) or ""
    if not str(raw).strip():
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    meta = parsed.get(R2_JSON_KEY)
    if not isinstance(meta, dict):
        return None
    key = str(meta.get("object_key") or "").strip()
    if not key:
        return None
    return meta


def media_has_r2(media) -> bool:
    return r2_meta_from_media(media) is not None


def _merge_r2_into_classification(media, r2_meta: dict[str, Any]) -> None:
    existing: dict[str, Any] = {}
    raw = getattr(media, "classification_json", None) or ""
    if str(raw).strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                existing = parsed
        except Exception:
            existing = {}
    existing[R2_JSON_KEY] = r2_meta
    media.classification_json = json.dumps(existing, ensure_ascii=False)


def _guess_ext(media_type: str | None, content_type: str | None) -> str:
    if content_type:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if ext:
            return ext.lstrip(".")
    mt = (media_type or "").lower()
    if mt == "video":
        return "mp4"
    if mt == "gif":
        return "gif"
    return "jpg"


def object_key_for_media(media, *, content_type: str | None = None) -> str:
    ext = _guess_ext(getattr(media, "media_type", None), content_type)
    fid = str(getattr(media, "file_unique_id", None) or media.id).strip() or str(media.id)
    safe = "".join(c if c.isalnum() or c in "._-" else "-" for c in fid)[:80]
    return f"{OBJECT_KEY_PREFIX}/{int(media.id)}/{safe}.{ext}"


def _download_media_bytes_sync(media_id: int) -> tuple[bytes, str]:
    """Telethon / local download on the worker event loop."""
    from app.api.media import MediaFetchContext, _fetch_media_bytes_and_type
    from app.database.session import SessionLocal
    from app.models.media import Media
    from app.services.import_job_runner import _run_on_worker_loop

    db = SessionLocal()
    try:
        row = db.query(Media).filter(Media.id == int(media_id)).first()
        if not row:
            raise ValueError(f"media {media_id} not found")
        ctx = MediaFetchContext(
            id=int(row.id),
            source_channel=row.source_channel,
            telegram_message_id=row.telegram_message_id,
            media_type=row.media_type,
        )
    finally:
        db.close()

    return _run_on_worker_loop(_fetch_media_bytes_and_type(ctx))


def export_one_media_to_r2(db: Session, media_id: int, *, force: bool = False) -> dict[str, Any]:
    """Download one Media row and PUT to R2. Idempotent unless force=True."""
    from app.models.media import Media
    from app.services.r2_promo_upload import upload_bytes_to_r2

    media = db.query(Media).filter(Media.id == int(media_id)).first()
    if not media:
        return {"ok": False, "media_id": media_id, "error": "not_found"}

    existing = r2_meta_from_media(media)
    if existing and not force:
        return {
            "ok": True,
            "media_id": media_id,
            "skipped": True,
            "object_key": existing.get("object_key"),
            "direct_url": existing.get("direct_url"),
        }

    try:
        data, content_type = _download_media_bytes_sync(int(media_id))
    except Exception as e:
        logger.warning("storage_hub r2 download failed media_id=%s: %s", media_id, e)
        return {"ok": False, "media_id": media_id, "error": f"download:{e}"}

    if not data:
        return {"ok": False, "media_id": media_id, "error": "empty_download"}

    key = object_key_for_media(media, content_type=content_type)
    filename = key.rsplit("/", 1)[-1]
    try:
        # Large videos — allow longer PUT
        timeout = 300.0 if len(data) > 5_000_000 else 120.0
        uploaded = upload_bytes_to_r2(
            data,
            filename=filename,
            object_key=key,
            content_type=content_type or "application/octet-stream",
            timeout=timeout,
        )
    except Exception as e:
        logger.warning("storage_hub r2 upload failed media_id=%s: %s", media_id, e)
        return {"ok": False, "media_id": media_id, "error": f"upload:{e}"}

    meta = {
        "object_key": uploaded["object_key"],
        "direct_url": uploaded["direct_url"],
        "bucket": uploaded.get("bucket"),
        "provider": uploaded.get("provider"),
        "byte_size": len(data),
        "content_type": content_type,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    _merge_r2_into_classification(media, meta)
    db.commit()
    logger.info(
        "storage_hub r2 exported media_id=%s key=%s bytes=%s",
        media_id,
        meta["object_key"],
        len(data),
    )
    return {"ok": True, "media_id": media_id, "skipped": False, **meta}


def iter_storage_hub_media_ids(
    db: Session,
    *,
    since_id: int = 0,
    limit: int = 20,
    only_missing_r2: bool = True,
    status: str = "approved",
) -> list[int]:
    from app.api.media import _apply_storage_hub_export_filter
    from app.models.media import Media

    q = db.query(Media.id).filter(Media.id > int(since_id or 0))
    st = (status or "").strip().lower()
    if st:
        q = q.filter(Media.status == st)
    q = _apply_storage_hub_export_filter(q, db)
    fetch_limit = max(1, min(int(limit), 100)) * (3 if only_missing_r2 else 1)
    # Newest missing first — Beat always passes since_id=0; ascending scan stuck on
    # oldest rows that already have r2 while high-id hub deposits never export.
    if only_missing_r2:
        if int(since_id or 0) > 0:
            q = q.filter(Media.id < int(since_id))
        rows = q.order_by(Media.id.desc()).limit(fetch_limit).all()
    else:
        rows = q.order_by(Media.id.asc()).limit(fetch_limit).all()
    ids = [int(r[0]) for r in rows]
    if not only_missing_r2:
        return ids[: max(1, min(int(limit), 100))]

    out: list[int] = []
    for mid in ids:
        m = db.query(Media).filter(Media.id == mid).first()
        if m and not media_has_r2(m):
            out.append(mid)
        if len(out) >= max(1, min(int(limit), 100)):
            break
    return out


def export_storage_hub_batch(
    db: Session,
    *,
    since_id: int = 0,
    limit: int = 10,
    only_missing_r2: bool = True,
) -> dict[str, Any]:
    ids = iter_storage_hub_media_ids(
        db, since_id=since_id, limit=limit, only_missing_r2=only_missing_r2
    )
    results = []
    exported = 0
    skipped = 0
    failed = 0
    max_id = since_id
    min_id = since_id or None
    for mid in ids:
        max_id = max(max_id, mid)
        min_id = mid if min_id is None else min(min_id, mid)
        r = export_one_media_to_r2(db, mid)
        results.append(r)
        if not r.get("ok"):
            failed += 1
        elif r.get("skipped"):
            skipped += 1
        else:
            exported += 1
    return {
        "ok": failed == 0,
        "count": len(ids),
        "exported": exported,
        "skipped": skipped,
        "failed": failed,
        "next_since_id": (min_id if only_missing_r2 and min_id is not None else max_id),
        "results": results,
    }
