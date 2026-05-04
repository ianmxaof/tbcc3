import io
import logging
from collections import defaultdict
from typing import NamedTuple

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import update
from sqlalchemy.orm import Session
from telethon.errors.rpcerrorlist import FileReferenceExpiredError

from app.database.session import SessionLocal, get_db
from app.schemas.common import orm_to_dict
from app.services.media_sniff import sniff_media_kind
from app.services.tbcc_media_url import looks_like_tbcc_internal_media_url

logger = logging.getLogger(__name__)

router = APIRouter()


class MediaFetchContext(NamedTuple):
    """ORM-free snapshot for downloads — keeps DB sessions from spanning slow I/O."""

    id: int
    source_channel: str | None
    telegram_message_id: int | None
    media_type: str | None


def _coerce_single_message(messages):
    """Telethon returns Message for scalar ids, list for multi-id requests."""
    if messages is None:
        return None
    if isinstance(messages, (list, tuple)):
        return messages[0] if messages else None
    return messages


def _image_bytes_to_thumbnail_jpeg(data: bytes, max_edge: int = 320) -> bytes | None:
    """Downscale image-like bytes to JPEG for dashboard grids (lighter + more reliable than full-size <img>)."""
    try:
        from PIL import Image, ImageOps

        im = Image.open(io.BytesIO(data))
        im.seek(0)
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "P"):
            im = im.convert("RGB")
        elif im.mode == "L":
            im = im.convert("RGB")
        elif im.mode != "RGB":
            try:
                im = im.convert("RGB")
            except Exception:
                return None
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


def _split_tag_tokens(raw: str | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for part in str(raw).split(","):
        t = part.strip().lower()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _smoothed_rate(pos: int, total: int, prior: float, strength: float = 6.0) -> float:
    if total <= 0:
        return prior
    return float((pos + (prior * strength)) / (total + strength))


def _build_pool_preference_stats(db: Session, pool_id: int) -> dict:
    from app.models.media import Media

    rows = (
        db.query(Media.status, Media.source_channel, Media.media_type, Media.tags, Media.nsfw_tier)
        .filter(
            Media.pool_id == pool_id,
            Media.status.in_(("approved", "posted", "rejected")),
        )
        .order_by(Media.id.desc())
        .limit(5000)
        .all()
    )
    pos_total = 0
    all_total = 0
    source_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    type_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    tag_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    tier_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    for status, source_channel, media_type, tags, nsfw_tier in rows:
        ok = status in ("approved", "posted")
        all_total += 1
        if ok:
            pos_total += 1

        src = (str(source_channel or "").strip().lower())[:512]
        if src:
            source_counts[src][1] += 1
            if ok:
                source_counts[src][0] += 1

        mt = str(media_type or "").strip().lower()
        if mt:
            type_counts[mt][1] += 1
            if ok:
                type_counts[mt][0] += 1

        tier = str(nsfw_tier or "").strip().lower()
        if tier:
            tier_counts[tier][1] += 1
            if ok:
                tier_counts[tier][0] += 1

        for tg in _split_tag_tokens(tags):
            tag_counts[tg][1] += 1
            if ok:
                tag_counts[tg][0] += 1

    base = float(pos_total / all_total) if all_total > 0 else 0.5
    return {
        "base": base,
        "source": {k: _smoothed_rate(v[0], v[1], base) for k, v in source_counts.items()},
        "type": {k: _smoothed_rate(v[0], v[1], base) for k, v in type_counts.items()},
        "tag": {k: _smoothed_rate(v[0], v[1], base) for k, v in tag_counts.items()},
        "tier": {k: _smoothed_rate(v[0], v[1], base) for k, v in tier_counts.items()},
    }


def _recommendation_score(media, stats: dict) -> float:
    base = float(stats.get("base", 0.5))
    source_rate = stats["source"].get((str(media.source_channel or "").strip().lower())[:512], base)
    type_rate = stats["type"].get(str(media.media_type or "").strip().lower(), base)
    tier_rate = stats["tier"].get(str(media.nsfw_tier or "").strip().lower(), base)
    tags = _split_tag_tokens(media.tags)
    if tags:
        tag_rates = [stats["tag"].get(tg, base) for tg in tags[:12]]
        tag_rate = float(sum(tag_rates) / len(tag_rates))
    else:
        tag_rate = base
    # Weighted rule score; tiny recency bump keeps ties fresh.
    return (source_rate * 0.34) + (tag_rate * 0.32) + (type_rate * 0.20) + (tier_rate * 0.10) + (base * 0.04)


async def _fetch_media_bytes_and_type(ctx: MediaFetchContext) -> tuple[bytes, str]:
    """HTTP(S) direct URL, or download from Telegram Saved Messages (indexed by telegram_message_id)."""
    url = str(ctx.source_channel or "").strip()
    # Never HTTP-fetch our own /media/{id}/thumbnail URLs (loopback + Vite proxy → 502).
    if url.startswith(("http://", "https://")) and looks_like_tbcc_internal_media_url(url):
        url = ""

    from app.services.telegram_admin import get_telegram_client

    async def _download_from_saved(client, msg_id: int):
        """Download bytes from Saved Messages; BytesIO is more reliable than passing `bytes` type."""
        messages = await client.get_messages("me", ids=msg_id)
        msg = _coerce_single_message(messages)
        if not msg or not msg.media:
            raise HTTPException(status_code=404, detail="Media not found in Telegram")
        buf = io.BytesIO()
        await client.download_media(msg, file=buf)
        out = buf.getvalue()
        if not out:
            # File reference may be stale — refetch message once (Telegram invalidates refs periodically).
            messages = await client.get_messages("me", ids=msg.id)
            msg = _coerce_single_message(messages)
            if not msg or not msg.media:
                raise HTTPException(status_code=404, detail="Media not found in Telegram after refresh")
            buf = io.BytesIO()
            await client.download_media(msg, file=buf)
            out = buf.getvalue()
        return out

    # Scraped / Telethon-imported rows store the origin as https://t.me/channel — that is HTML, not bytes.
    # The real file is always in Saved Messages at telegram_message_id (same as poster / album pipeline).
    if ctx.telegram_message_id is not None:
        try:
            client = await get_telegram_client()
            try:
                data = await _download_from_saved(client, ctx.telegram_message_id)
            except FileReferenceExpiredError:
                logger.warning(
                    "File reference expired for media id=%s msg=%s; refetching",
                    ctx.id,
                    ctx.telegram_message_id,
                )
                messages = await client.get_messages("me", ids=ctx.telegram_message_id)
                msg = _coerce_single_message(messages)
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
            logger.exception("Telegram download failed for media id=%s", ctx.id)
            raise HTTPException(status_code=502, detail="Telegram download failed: " + str(e)) from e

        if not data:
            raise HTTPException(status_code=502, detail="Empty download")
        kind, ext = sniff_media_kind(data)
        ct = _MIME_FROM_EXT.get(ext, "application/octet-stream")
        return data, ct

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

    raise HTTPException(status_code=404, detail="No Telegram message id or fetchable URL for this media")


async def _fetch_saved_message_thumbnail_bytes(ctx: MediaFetchContext) -> tuple[bytes, str] | None:
    """
    Best-effort image thumbnail from Telegram Saved Messages for video/doc rows.
    Returns (bytes, mime) or None when no thumb is available.
    """
    if ctx.telegram_message_id is None:
        return None
    from app.services.telegram_admin import get_telegram_client

    try:
        client = await get_telegram_client()
        messages = await client.get_messages("me", ids=ctx.telegram_message_id)
        msg = _coerce_single_message(messages)
        if not msg or not msg.media:
            return None
        # -1 asks Telethon/Telegram for the largest available thumbnail size.
        buf = io.BytesIO()
        await client.download_media(msg, file=buf, thumb=-1)
        data = buf.getvalue()
        if not data:
            return None
        jpeg = _image_bytes_to_thumbnail_jpeg(data)
        if jpeg:
            return jpeg, "image/jpeg"
        kind, ext = sniff_media_kind(data)
        if kind in ("photo", "gif"):
            return data, _MIME_FROM_EXT.get(ext, "image/jpeg")
        return None
    except Exception:
        logger.debug("saved-message thumbnail fetch skipped for media id=%s", ctx.id, exc_info=True)
        return None


@router.get("/")
def list_media(
    db: Session = Depends(get_db),
    status: str | None = None,
    pool_id: int | None = None,
    tag: str | None = None,
    tag_slug: str | None = None,
    sort: str | None = None,
    target_pool_id: int | None = None,
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
    items = q.order_by(Media.id.desc()).limit(200).all()
    sort_mode = (sort or "").strip().lower()
    model_pool_id = target_pool_id if target_pool_id is not None else pool_id
    if sort_mode == "recommended" and model_pool_id is not None and items:
        stats = _build_pool_preference_stats(db, int(model_pool_id))
        scored: list[dict] = []
        for m in items:
            d = orm_to_dict(m)
            d["recommendation_score"] = round(_recommendation_score(m, stats), 6)
            scored.append(d)
        scored.sort(key=lambda x: (float(x.get("recommendation_score", 0.0)), int(x.get("id") or 0)), reverse=True)
        return scored
    return [orm_to_dict(m) for m in items]


@router.get("/{media_id}")
def get_media(media_id: int, db: Session = Depends(get_db)):
    from app.models.media import Media
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        return {"error": "Not found"}
    return orm_to_dict(media)


@router.get("/{media_id}/thumbnail")
async def get_media_thumbnail(media_id: int):
    """Grid / preview: proxy URL or download from Telegram Saved Messages."""
    from app.models.media import Media

    db = SessionLocal()
    try:
        media = db.query(Media).filter(Media.id == media_id).first()
        if not media:
            raise HTTPException(status_code=404, detail="Not found")
        ctx = MediaFetchContext(
            id=int(media.id),
            source_channel=media.source_channel,
            telegram_message_id=media.telegram_message_id,
            media_type=media.media_type,
        )
    finally:
        db.close()

    mt = (ctx.media_type or "").lower()
    if mt == "video":
        # For <img> grid thumbnails, prefer Telegram's still preview instead of raw video bytes.
        thumb = await _fetch_saved_message_thumbnail_bytes(ctx)
        if thumb is not None:
            data, mime = thumb
        else:
            data, mime = await _fetch_media_bytes_and_type(ctx)
    else:
        data, mime = await _fetch_media_bytes_and_type(ctx)
        jpeg = _image_bytes_to_thumbnail_jpeg(data)
        if jpeg:
            data = jpeg
            mime = "image/jpeg"
    return StreamingResponse(
        iter([data]),
        media_type=mime,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/{media_id}/file")
async def get_media_file(media_id: int):
    """Full-resolution bytes (same source as thumbnail; used by dashboard lightbox)."""
    from app.models.media import Media

    db = SessionLocal()
    try:
        media = db.query(Media).filter(Media.id == media_id).first()
        if not media:
            raise HTTPException(status_code=404, detail="Not found")
        ctx = MediaFetchContext(
            id=int(media.id),
            source_channel=media.source_channel,
            telegram_message_id=media.telegram_message_id,
            media_type=media.media_type,
        )
    finally:
        db.close()

    data, mime = await _fetch_media_bytes_and_type(ctx)
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
    try:
        id_ints = [int(x) for x in ids]
    except (TypeError, ValueError):
        return {"updated": 0, "error": "Invalid ids or status"}
    stmt = update(Media).where(Media.id.in_(id_ints)).values(status=status)
    result = db.execute(stmt)
    db.commit()
    return {"updated": int(result.rowcount or 0)}


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


@router.delete("/{media_id}")
def delete_media(media_id: int, db: Session = Depends(get_db)):
    """Remove a media row from TBCC (does not delete the Telegram Saved Messages message)."""
    from app.models.media import Media

    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(media)
    db.commit()
    return {"deleted": media_id}


@router.patch("/bulk/move-pool")
def bulk_move_pool(data: dict = Body(...), db: Session = Depends(get_db)):
    """
    Move media rows to another pool (skips rows that would violate per-pool dedup).

    Uses one pass over deduped ids + one UPDATE — avoids per-row queries and autoflush
    ordering bugs that made large gallery moves look random.
    """
    from app.models.media import Media

    ids = data.get("ids") or []
    pool_id = data.get("pool_id")
    if not ids or pool_id is None:
        return {"updated": 0, "skipped_duplicate_in_target_pool": 0, "error": "Need ids and pool_id"}
    try:
        pid = int(pool_id)
    except (TypeError, ValueError):
        return {"updated": 0, "skipped_duplicate_in_target_pool": 0, "error": "Invalid pool_id"}

    id_list: list[int] = []
    seen_ids: set[int] = set()
    for mid in ids:
        try:
            mid_int = int(mid)
        except (TypeError, ValueError):
            continue
        if mid_int in seen_ids:
            continue
        seen_ids.add(mid_int)
        id_list.append(mid_int)

    if not id_list:
        return {"updated": 0, "skipped_duplicate_in_target_pool": 0, "error": None}

    medias = {m.id: m for m in db.query(Media).filter(Media.id.in_(id_list)).all()}

    # FIDs already present in the target pool from rows we are NOT moving (avoid self-conflict).
    target_fid_rows = (
        db.query(Media.file_unique_id)
        .filter(
            Media.pool_id == pid,
            Media.id.notin_(id_list),
            Media.file_unique_id.isnot(None),
            Media.file_unique_id != "",
        )
        .all()
    )
    target_fids = {str(r[0]).strip() for r in target_fid_rows if r[0] and str(r[0]).strip()}

    seen_batch_fids: set[str] = set()
    skipped_dup = 0
    to_move: list[int] = []

    for mid_int in id_list:
        m = medias.get(mid_int)
        if not m:
            continue
        fid = (m.file_unique_id or "").strip()
        if fid:
            if fid in target_fids or fid in seen_batch_fids:
                skipped_dup += 1
                continue
            seen_batch_fids.add(fid)
        to_move.append(mid_int)

    if to_move:
        stmt = update(Media).where(Media.id.in_(to_move)).values(pool_id=pid)
        result = db.execute(stmt)
        db.commit()
        updated = int(result.rowcount or 0)
    else:
        updated = 0

    if skipped_dup and len(id_list) >= 10:
        logger.info(
            "bulk_move_pool pool_id=%s requested=%s moved=%s skipped_dup=%s",
            pid,
            len(id_list),
            updated,
            skipped_dup,
        )

    return {"updated": updated, "skipped_duplicate_in_target_pool": skipped_dup, "error": None}


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


@router.post("/{media_id}/auto-tag-llm")
def queue_auto_tag_llm(media_id: int, db: Session = Depends(get_db)):
    """
    Queue Celery job to tag this image with OpenAI vision against existing /tags catalog.
    Requires TBCC_OPENAI_API_KEY. Skips video/documents in worker. Manual trigger (not only import).
    """
    from app.models.media import Media

    m = db.query(Media).filter(Media.id == media_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        from app.workers.media_auto_tag_worker import auto_tag_media_llm

        async_result = auto_tag_media_llm.delay(int(media_id))
        return {"queued": True, "media_id": int(media_id), "task_id": async_result.id}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Celery unavailable: {e}") from e


@router.post("/bulk/auto-tag-llm")
def bulk_queue_auto_tag_llm(data: dict = Body(...), db: Session = Depends(get_db)):
    """Queue vision auto-tag for many ids (photos; worker skips unsupported types)."""
    from app.models.media import Media

    ids = data.get("ids") or []
    if not ids:
        return {"queued": 0, "error": "Need ids"}
    id_list: list[int] = []
    for x in ids:
        try:
            id_list.append(int(x))
        except (TypeError, ValueError):
            continue
    if not id_list:
        return {"queued": 0, "error": "No valid ids"}
    try:
        from app.workers.media_auto_tag_worker import auto_tag_media_llm
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Celery unavailable: {e}") from e
    n = 0
    task_ids: list[str] = []
    for mid in id_list:
        if not db.query(Media).filter(Media.id == mid).first():
            continue
        r = auto_tag_media_llm.delay(mid)
        task_ids.append(r.id)
        n += 1
    return {"queued": n, "task_ids": task_ids[:50]}
