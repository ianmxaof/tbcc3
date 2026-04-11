import io
import logging

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from telethon.errors.rpcerrorlist import FileReferenceExpiredError

from app.database.session import get_db
from app.schemas.common import orm_to_dict
from app.services.media_sniff import sniff_media_kind
from app.services.tbcc_media_url import looks_like_tbcc_internal_media_url

logger = logging.getLogger(__name__)

router = APIRouter()

_MIME_FROM_EXT = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
    "mp4": "video/mp4",
    "webm": "video/webm",
    "avi": "video/x-msvideo",
    "bin": "application/octet-stream",
}


async def _fetch_media_bytes_and_type(media) -> tuple[bytes, str]:
    """HTTP(S) proxy or download from Telegram Saved Messages (indexed by telegram_message_id)."""
    from app.models.media import Media

    if not isinstance(media, Media):
        raise HTTPException(status_code=404, detail="Not found")
    url = str(media.source_channel or "").strip()
    # Never HTTP-fetch our own /media/{id}/thumbnail URLs (loopback + Vite proxy → 502).
    if url.startswith(("http://", "https://")) and looks_like_tbcc_internal_media_url(url):
        url = ""
    if url.startswith(("http://", "https://")):
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
                r = await client.get(url)
                r.raise_for_status()
                data = r.content
                ct = (r.headers.get("content-type") or "").split(";")[0].strip()
                if not ct or ct == "application/octet-stream":
                    kind, ext = sniff_media_kind(data)
                    ct = _MIME_FROM_EXT.get(ext, "application/octet-stream")
                return data, ct
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail="Failed to fetch media URL") from e

    from app.services.telegram_admin import get_telegram_client

    async def _download_from_saved(client, msg_id: int):
        """Download bytes from Saved Messages; BytesIO is more reliable than passing `bytes` type."""
        messages = await client.get_messages("me", ids=msg_id)
        msg = messages[0] if messages else None
        if not msg or not msg.media:
            raise HTTPException(status_code=404, detail="Media not found in Telegram")
        buf = io.BytesIO()
        await client.download_media(msg, file=buf)
        out = buf.getvalue()
        if not out:
            # File reference may be stale — refetch message once (Telegram invalidates refs periodically).
            messages = await client.get_messages("me", ids=msg.id)
            msg = messages[0] if messages else None
            if not msg or not msg.media:
                raise HTTPException(status_code=404, detail="Media not found in Telegram after refresh")
            buf = io.BytesIO()
            await client.download_media(msg, file=buf)
            out = buf.getvalue()
        return out

    try:
        client = await get_telegram_client()
        try:
            data = await _download_from_saved(client, media.telegram_message_id)
        except FileReferenceExpiredError:
            logger.warning("File reference expired for media id=%s msg=%s; refetching", media.id, media.telegram_message_id)
            messages = await client.get_messages("me", ids=media.telegram_message_id)
            msg = messages[0] if messages else None
            if not msg or not msg.media:
                raise HTTPException(status_code=404, detail="Media not found in Telegram") from None
            buf = io.BytesIO()
            await client.download_media(msg, file=buf)
            data = buf.getvalue()
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e) or "Telegram not configured") from e
    except Exception as e:
        logger.exception("Telegram download failed for media id=%s", getattr(media, "id", "?"))
        raise HTTPException(status_code=502, detail="Telegram download failed: " + str(e)) from e

    if not data:
        raise HTTPException(status_code=502, detail="Empty download")
    kind, ext = sniff_media_kind(data)
    ct = _MIME_FROM_EXT.get(ext, "application/octet-stream")
    return data, ct


@router.get("/")
def list_media(
    db: Session = Depends(get_db),
    status: str | None = None,
    pool_id: int | None = None,
    tag: str | None = None,
    tag_slug: str | None = None,
):
    from app.models.media import Media
    from app.models.tbcc_tag import TbccTag, MediaTagLink

    q = db.query(Media)
    if status:
        q = q.filter(Media.status == status)
    if pool_id is not None:
        q = q.filter(Media.pool_id == pool_id)
    if tag_slug and tag_slug.strip():
        tid = (
            db.query(TbccTag.id)
            .filter(TbccTag.slug == tag_slug.strip().lower())
            .scalar()
        )
        if tid is not None:
            q = q.join(MediaTagLink, MediaTagLink.media_id == Media.id).filter(
                MediaTagLink.tag_id == tid
            )
        else:
            q = q.filter(Media.id == -1)
    elif tag and tag.strip():
        needle = f"%{tag.strip().lower()}%"
        q = q.filter(Media.tags.isnot(None)).filter(Media.tags.ilike(needle))
    return [orm_to_dict(m) for m in q.order_by(Media.id.desc()).limit(200).all()]


@router.get("/{media_id}")
def get_media(media_id: int, db: Session = Depends(get_db)):
    from app.models.media import Media
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        return {"error": "Not found"}
    return orm_to_dict(media)


@router.get("/{media_id}/thumbnail")
async def get_media_thumbnail(media_id: int, db: Session = Depends(get_db)):
    """Grid / preview: proxy URL or download from Telegram Saved Messages."""
    from app.models.media import Media

    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Not found")
    data, mime = await _fetch_media_bytes_and_type(media)
    return StreamingResponse(
        iter([data]),
        media_type=mime,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/{media_id}/file")
async def get_media_file(media_id: int, db: Session = Depends(get_db)):
    """Full-resolution bytes (same source as thumbnail; used by dashboard lightbox)."""
    from app.models.media import Media

    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Not found")
    data, mime = await _fetch_media_bytes_and_type(media)
    return StreamingResponse(
        iter([data]),
        media_type=mime,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.patch("/bulk")
def update_media_status_bulk(data: dict = Body(...), db: Session = Depends(get_db)):
    """Bulk update status for multiple media items."""
    from app.models.media import Media

    ids = data.get("ids") or []
    status = data.get("status")
    if status not in ("pending", "approved", "rejected", "posted") or not ids:
        return {"updated": 0, "error": "Invalid ids or status"}
    count = db.query(Media).filter(Media.id.in_(ids)).update({Media.status: status})
    db.commit()
    return {"updated": count}


@router.patch("/{media_id}")
def update_media_status(media_id: int, data: dict, db: Session = Depends(get_db)):
    from app.models.media import Media
    from app.services.media_tagging import replace_manual_tags_from_csv

    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        return {"error": "Not found"}
    status = data.get("status")
    if status in ("pending", "approved", "rejected", "posted"):
        media.status = status
    if "tags" in data and data["tags"] is not None:
        from app.services.media_tagging import merge_manual_tags_from_csv, replace_manual_tags_from_csv

        t = data.get("tags")
        val = (str(t).strip()[:2000]) if t else None
        if data.get("tags_merge") is True or data.get("merge") is True:
            merge_manual_tags_from_csv(db, media_id, val)
        else:
            replace_manual_tags_from_csv(db, media_id, val)
    if "source_channel" in data:
        sc = data.get("source_channel")
        if sc is None or (isinstance(sc, str) and not str(sc).strip()):
            media.source_channel = None
        else:
            media.source_channel = str(sc).strip()[:4096]
    if "pool_id" in data and data["pool_id"] is not None:
        try:
            pid = int(data["pool_id"])
        except (TypeError, ValueError):
            pass
        else:
            if pid != media.pool_id:
                fid = (media.file_unique_id or "").strip()
                if fid:
                    conflict = (
                        db.query(Media)
                        .filter(
                            Media.pool_id == pid,
                            Media.file_unique_id == fid,
                            Media.id != media_id,
                        )
                        .first()
                    )
                    if conflict:
                        return {
                            "error": "Another media row in the target pool already has this file (dedup).",
                            "skipped_duplicate_in_target_pool": True,
                        }
                media.pool_id = pid
    db.commit()
    db.refresh(media)
    return orm_to_dict(media)


@router.patch("/bulk/move-pool")
def bulk_move_pool(data: dict = Body(...), db: Session = Depends(get_db)):
    """Move media rows to another pool (skips rows that would violate per-pool dedup)."""
    from app.models.media import Media

    ids = data.get("ids") or []
    pool_id = data.get("pool_id")
    if not ids or pool_id is None:
        return {"updated": 0, "error": "Need ids and pool_id"}
    try:
        pid = int(pool_id)
    except (TypeError, ValueError):
        return {"updated": 0, "error": "Invalid pool_id"}
    n = 0
    skipped_dup = 0
    for mid in ids:
        try:
            mid_int = int(mid)
        except (TypeError, ValueError):
            continue
        m = db.query(Media).filter(Media.id == mid_int).first()
        if not m:
            continue
        fid = (m.file_unique_id or "").strip()
        if fid:
            conflict = (
                db.query(Media)
                .filter(Media.pool_id == pid, Media.file_unique_id == fid, Media.id != mid_int)
                .first()
            )
            if conflict:
                skipped_dup += 1
                continue
        m.pool_id = pid
        n += 1
    db.commit()
    return {"updated": n, "skipped_duplicate_in_target_pool": skipped_dup}


@router.patch("/bulk/tags")
def bulk_set_tags(data: dict = Body(...), db: Session = Depends(get_db)):
    from app.models.media import Media
    from app.services.media_tagging import merge_manual_tags_from_csv, replace_manual_tags_from_csv

    ids = data.get("ids") or []
    tags = data.get("tags")
    if not ids:
        return {"updated": 0, "error": "Need ids"}
    val = (str(tags).strip()[:2000]) if tags else None
    merge = data.get("tags_merge") is True or data.get("merge") is True
    fn = merge_manual_tags_from_csv if merge else replace_manual_tags_from_csv
    n = 0
    for mid in ids:
        try:
            mid_int = int(mid)
        except (TypeError, ValueError):
            continue
        if not db.query(Media).filter(Media.id == mid_int).first():
            continue
        fn(db, mid_int, val)
        n += 1
    return {"updated": n}
