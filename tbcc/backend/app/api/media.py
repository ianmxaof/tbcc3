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
):
    from app.models.media import Media
    q = db.query(Media)
    if status:
        q = q.filter(Media.status == status)
    if pool_id is not None:
        q = q.filter(Media.pool_id == pool_id)
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
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        return {"error": "Not found"}
    status = data.get("status")
    if status in ("pending", "approved", "rejected", "posted"):
        media.status = status
        db.commit()
        db.refresh(media)
    return orm_to_dict(media)
