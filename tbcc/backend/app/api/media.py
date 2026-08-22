import asyncio
import io
import json
import logging
import os
from collections import defaultdict
from typing import NamedTuple

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from telethon.errors.rpcerrorlist import FileReferenceExpiredError

from app.database.session import SessionLocal, get_db
from app.schemas.common import orm_to_dict
from app.services.media_sniff import sniff_media_kind
from app.services.tbcc_media_url import looks_like_tbcc_internal_media_url

logger = logging.getLogger(__name__)

router = APIRouter()


def _norm_media_fid(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


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


def _media_list_limit(requested: int | None = None) -> int:
    """Cap on rows returned by the media list.

    Defaults to TBCC_MEDIA_LIST_LIMIT (100) — the operator wants a small, fast library,
    not thousands of rows hammering thumbnail fetches. A per-request ?limit may lower it
    but never exceed the configured ceiling.
    """
    raw = (os.getenv("TBCC_MEDIA_LIST_LIMIT") or "100").strip()
    try:
        ceiling = max(1, int(raw))
    except ValueError:
        ceiling = 100
    if requested is not None and requested > 0:
        return min(requested, ceiling)
    return ceiling


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


def _extract_storage_hub_chat_ident(source_channel: str | None) -> str:
    """Unwrap a topic-qualified source_channel to the bare chat id.

    Index-only channel/topic deposits (_index_channel_message) store
    source_channel as ``"telegram:{chat_id}#topic:{thread_id}"`` when the
    source label carries a topic, not the bare chat id. Downstream Telethon
    lookups (resolve_telethon_entity, get_messages) need the bare id.
    """
    sc = (source_channel or "").strip()
    if sc.startswith("telegram:"):
        sc = sc[len("telegram:"):]
    hash_idx = sc.find("#")
    if hash_idx != -1:
        sc = sc[:hash_idx]
    return sc.strip()


def _is_storage_hub_source(source_channel: str | None) -> bool:
    from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT

    sc = _extract_storage_hub_chat_ident(source_channel)
    if not sc:
        return False
    if sc == STORAGE_HUB_IDENT:
        return True
    try:
        return int(sc) == int(STORAGE_HUB_IDENT)
    except ValueError:
        return False


async def _download_from_chat(client, chat_ident: str, msg_id: int) -> bytes:
    """Download bytes from a Storage Hub in-chat message (index-only deposit rows)."""
    from app.utils.telegram_peer import resolve_telethon_entity

    entity = await resolve_telethon_entity(client, chat_ident)
    messages = await client.get_messages(entity, ids=int(msg_id))
    msg = _coerce_single_message(messages)
    if not msg or not msg.media:
        raise HTTPException(status_code=404, detail="Media not found in Storage Hub topic")
    buf = io.BytesIO()
    await client.download_media(msg, file=buf)
    out = buf.getvalue()
    if not out:
        messages = await client.get_messages(entity, ids=int(msg_id))
        msg = _coerce_single_message(messages)
        if not msg or not msg.media:
            raise HTTPException(status_code=404, detail="Media not found in Storage Hub after refresh")
        buf = io.BytesIO()
        await client.download_media(msg, file=buf)
        out = buf.getvalue()
    return out


async def _download_from_saved(client, msg_id: int) -> bytes:
    """Download bytes from Saved Messages; BytesIO is more reliable than passing `bytes` type."""
    messages = await client.get_messages("me", ids=msg_id)
    msg = _coerce_single_message(messages)
    if not msg or not msg.media:
        raise HTTPException(status_code=404, detail="Media not found in Telegram")
    buf = io.BytesIO()
    await client.download_media(msg, file=buf)
    out = buf.getvalue()
    if not out:
        messages = await client.get_messages("me", ids=msg.id)
        msg = _coerce_single_message(messages)
        if not msg or not msg.media:
            raise HTTPException(status_code=404, detail="Media not found in Telegram after refresh")
        buf = io.BytesIO()
        await client.download_media(msg, file=buf)
        out = buf.getvalue()
    return out


async def _fetch_media_bytes_and_type(ctx: MediaFetchContext) -> tuple[bytes, str]:
    """Local pool file, HTTP(S) direct URL, or download from Telegram Saved Messages."""
    from app.database.session import SessionLocal
    from app.models.media import Media
    from app.services.local_media_storage import LOCAL_TELEGRAM_MESSAGE_ID, local_media_path

    if ctx.telegram_message_id == LOCAL_TELEGRAM_MESSAGE_ID:
        db = SessionLocal()
        try:
            row = db.query(Media).filter(Media.id == ctx.id).first()
            if row:
                p = local_media_path(row)
                if p and p.is_file():
                    data = p.read_bytes()
                    kind, ext = sniff_media_kind(data)
                    ct = _MIME_FROM_EXT.get(ext, "application/octet-stream")
                    return data, ct
        finally:
            db.close()
        raise HTTPException(status_code=404, detail="Local media file missing for this pool item")

    url = str(ctx.source_channel or "").strip()
    # Never HTTP-fetch our own /media/{id}/thumbnail URLs (loopback + Vite proxy → 502).
    if url.startswith(("http://", "https://")) and looks_like_tbcc_internal_media_url(url):
        url = ""

    from app.services.telegram_admin import run_telegram_io

    # Scraped / Telethon-imported rows store the origin as https://t.me/channel — that is HTML, not bytes.
    # The real file is always in Saved Messages at telegram_message_id (same as poster / album pipeline).
    if ctx.telegram_message_id is not None:

        hub_ident = _extract_storage_hub_chat_ident(ctx.source_channel)
        use_hub = _is_storage_hub_source(hub_ident)

        async def _download_job(storage):
            client = storage.client
            if use_hub:
                try:
                    return await _download_from_chat(client, hub_ident, int(ctx.telegram_message_id))
                except FileReferenceExpiredError:
                    logger.warning(
                        "File reference expired for hub media id=%s msg=%s; refetching",
                        ctx.id,
                        ctx.telegram_message_id,
                    )
                    return await _download_from_chat(client, hub_ident, int(ctx.telegram_message_id))
            try:
                return await _download_from_saved(client, ctx.telegram_message_id)
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
                return buf.getvalue()

        try:
            data = await run_telegram_io(_download_job)
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


async def _fetch_media_bytes_and_type_via_import(ctx: MediaFetchContext) -> tuple[bytes, str]:
    """Same as _fetch_media_bytes_and_type but uses admin_import.session (Celery enrich / imports)."""
    from app.services.local_media_storage import LOCAL_TELEGRAM_MESSAGE_ID, local_media_path

    if ctx.telegram_message_id == LOCAL_TELEGRAM_MESSAGE_ID:
        return await _fetch_media_bytes_and_type(ctx)

    url = str(ctx.source_channel or "").strip()
    if url.startswith(("http://", "https://")) and looks_like_tbcc_internal_media_url(url):
        url = ""

    if ctx.telegram_message_id is not None:
        from app.services.telegram_admin import run_telegram_import_io

        hub_ident = _extract_storage_hub_chat_ident(ctx.source_channel)
        use_hub = _is_storage_hub_source(hub_ident)

        async def _download_job(storage):
            client = storage.client
            if use_hub:
                try:
                    return await _download_from_chat(client, hub_ident, int(ctx.telegram_message_id))
                except FileReferenceExpiredError:
                    logger.warning(
                        "File reference expired for hub media id=%s msg=%s; refetching (import)",
                        ctx.id,
                        ctx.telegram_message_id,
                    )
                    return await _download_from_chat(client, hub_ident, int(ctx.telegram_message_id))
            try:
                return await _download_from_saved(client, ctx.telegram_message_id)
            except FileReferenceExpiredError:
                logger.warning(
                    "File reference expired for media id=%s msg=%s; refetching (import session)",
                    ctx.id,
                    ctx.telegram_message_id,
                )
                messages = await client.get_messages("me", ids=ctx.telegram_message_id)
                msg = _coerce_single_message(messages)
                if not msg or not msg.media:
                    raise HTTPException(status_code=404, detail="Media not found in Telegram") from None
                buf = io.BytesIO()
                await client.download_media(msg, file=buf)
                return buf.getvalue()

        try:
            data = await run_telegram_import_io(_download_job)
        except HTTPException:
            raise
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e) or "Telegram not configured") from e
        except Exception as e:
            logger.exception("Telegram import-session download failed for media id=%s", ctx.id)
            raise HTTPException(status_code=502, detail="Telegram download failed: " + str(e)) from e

        if not data:
            raise HTTPException(status_code=502, detail="Empty download")
        kind, ext = sniff_media_kind(data)
        ct = _MIME_FROM_EXT.get(ext, "application/octet-stream")
        return data, ct

    if url.startswith(("http://", "https://")):
        return await _fetch_media_bytes_and_type(ctx)

    raise HTTPException(status_code=404, detail="No Telegram message id or fetchable URL for this media")


async def _fetch_saved_message_thumbnail_bytes(ctx: MediaFetchContext) -> tuple[bytes, str] | None:
    """
    Best-effort image thumbnail from Telegram Saved Messages for video/doc rows.
    Returns (bytes, mime) or None when no thumb is available.
    """
    from app.services.local_media_storage import LOCAL_TELEGRAM_MESSAGE_ID

    if ctx.telegram_message_id is None:
        return None
    if ctx.telegram_message_id == LOCAL_TELEGRAM_MESSAGE_ID:
        try:
            data, mime = await _fetch_media_bytes_and_type(ctx)
            jpeg = _image_bytes_to_thumbnail_jpeg(data)
            if jpeg:
                return jpeg, "image/jpeg"
            if (ctx.media_type or "").lower() in ("photo", "gif") or "image" in (mime or "").lower():
                return data, mime
        except HTTPException:
            return None
        return None
    from app.services.telegram_admin import run_telegram_io

    async def _thumb_job(storage):
        client = storage.client
        messages = await client.get_messages("me", ids=ctx.telegram_message_id)
        msg = _coerce_single_message(messages)
        if not msg or not msg.media:
            return None
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

    try:
        return await run_telegram_io(_thumb_job)
    except Exception:
        logger.debug("saved-message thumbnail fetch skipped for media id=%s", ctx.id, exc_info=True)
        return None


def _gallery_page_limit(requested: int | None = None) -> int:
    """Per-pool gallery pages — smaller than the main library cap to avoid thumbnail storms."""
    raw = (os.getenv("TBCC_GALLERY_PAGE_SIZE") or "24").strip()
    try:
        ceiling = max(1, min(60, int(raw)))
    except ValueError:
        ceiling = 24
    if requested is not None and requested > 0:
        return min(requested, ceiling)
    return ceiling


def _media_row_dict(media, *, minimal: bool = False) -> dict:
    if not minimal:
        return orm_to_dict(media)
    return {
        "id": int(media.id),
        "media_type": media.media_type,
        "status": media.status,
        "pool_id": media.pool_id,
        "nsfw_tier": media.nsfw_tier,
    }


@router.get("/")
def list_media(
    db: Session = Depends(get_db),
    status: str | None = None,
    pool_id: int | None = None,
    tag: str | None = None,
    tag_slug: str | None = None,
    sort: str | None = None,
    target_pool_id: int | None = None,
    limit: int | None = None,
    before_id: int | None = None,
    fields: str | None = None,
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
    minimal = (fields or "").strip().lower() == "minimal"
    page_cap = _gallery_page_limit(limit) if minimal else _media_list_limit(limit)
    if before_id is not None and int(before_id) > 0:
        q = q.filter(Media.id < int(before_id))
    items = q.order_by(Media.id.desc()).limit(page_cap).all()
    sort_mode = (sort or "").strip().lower()
    model_pool_id = target_pool_id if target_pool_id is not None else pool_id
    if sort_mode == "recommended" and model_pool_id is not None and items:
        stats = _build_pool_preference_stats(db, int(model_pool_id))
        scored: list[dict] = []
        for m in items:
            d = _media_row_dict(m, minimal=minimal)
            d["recommendation_score"] = round(_recommendation_score(m, stats), 6)
            scored.append(d)
        scored.sort(key=lambda x: (float(x.get("recommendation_score", 0.0)), int(x.get("id") or 0)), reverse=True)
        return scored
    return [_media_row_dict(m, minimal=minimal) for m in items]


@router.get("/pending-summary")
def pending_media_summary(db: Session = Depends(get_db)):
    """Pending + in-queue approval counts (global and per pool) for dashboard backlog banners."""
    from app.models.content_pool import ContentPool
    from app.models.media import Media
    from sqlalchemy import case, func

    in_queue_statuses = ("pending", "approved")

    total_pending = (
        db.query(func.count(Media.id)).filter(Media.status == "pending").scalar() or 0
    )
    total_queue = (
        db.query(func.count(Media.id))
        .filter(Media.status.in_(in_queue_statuses))
        .scalar()
        or 0
    )
    rows = (
        db.query(
            ContentPool.id,
            ContentPool.name,
            func.sum(case((Media.status == "pending", 1), else_=0)).label("pending"),
            func.count(Media.id).label("queue_total"),
        )
        .join(Media, Media.pool_id == ContentPool.id)
        .filter(Media.status.in_(in_queue_statuses))
        .group_by(ContentPool.id, ContentPool.name)
        .order_by(func.sum(case((Media.status == "pending", 1), else_=0)).desc())
        .all()
    )
    # Media rows without a matching pool still count globally above; optional unassigned bucket:
    unassigned_pending = (
        db.query(func.count(Media.id))
        .filter(Media.status == "pending", Media.pool_id.is_(None))
        .scalar()
        or 0
    )
    unassigned_queue = (
        db.query(func.count(Media.id))
        .filter(Media.status.in_(in_queue_statuses), Media.pool_id.is_(None))
        .scalar()
        or 0
    )
    pools_out = [
        {
            "pool_id": int(pid),
            "pool_name": str(name or ""),
            "pending": int(pending or 0),
            "queue_total": int(queue_total or 0),
        }
        for pid, name, pending, queue_total in rows
    ]
    if unassigned_queue > 0:
        pools_out.append(
            {
                "pool_id": 0,
                "pool_name": "(no pool)",
                "pending": int(unassigned_pending),
                "queue_total": int(unassigned_queue),
            }
        )
    return {
        "total_pending": int(total_pending),
        "total_queue": int(total_queue),
        "pools": pools_out,
    }


_MEDIA_EXPORT_DEFAULT_LIMIT = 20
_MEDIA_EXPORT_MAX_LIMIT = 50


def _clamp_export_limit(limit: int | None) -> int:
    raw = int(limit) if limit is not None else _MEDIA_EXPORT_DEFAULT_LIMIT
    return max(1, min(raw, _MEDIA_EXPORT_MAX_LIMIT))


def _trusted_aof_pool_ids(db: Session) -> list[int]:
    """Content pools that receive Storage Hub /deposit copies (AOF network lanes)."""
    from app.data.aof_network import AOF_NETWORK_CHANNELS
    from app.models.content_pool import ContentPool

    names = [ch.pool_name for ch in AOF_NETWORK_CHANNELS]
    if not names:
        return []
    rows = db.query(ContentPool.id).filter(ContentPool.name.in_(names)).all()
    return [int(r[0]) for r in rows]


def _apply_storage_hub_export_filter(q, db: Session):
    """Storage Hub deposits: hangar topic labels or trusted AOF network pools."""
    from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT
    from app.models.media import Media

    hub_tail = STORAGE_HUB_IDENT.lstrip("-")
    clauses = [Media.source_channel.ilike(f"%{hub_tail}%")]
    pool_ids = _trusted_aof_pool_ids(db)
    if pool_ids:
        clauses.append(Media.pool_id.in_(pool_ids))
    return q.filter(or_(*clauses))


def _network_key_for_export_row(db: Session, media) -> str | None:
    from app.services.media_gatekeeper import expected_lane_for_storage_source
    from app.services.export_flywheel_service import network_key_for_pool

    nk = expected_lane_for_storage_source(media.source_channel)
    if nk:
        return nk
    if media.pool_id:
        return network_key_for_pool(db, int(media.pool_id))
    return None


def _pool_name_for_export_row(db: Session, pool_id: int | None) -> str | None:
    if not pool_id:
        return None
    from app.models.content_pool import ContentPool

    row = db.query(ContentPool.name).filter(ContentPool.id == int(pool_id)).first()
    return str(row[0]).strip() if row and row[0] else None


def _r2_fields_for_export(media) -> dict:
    from app.services.storage_hub_r2_export import r2_meta_from_media

    meta = r2_meta_from_media(media) or {}
    object_key = str(meta.get("object_key") or "").strip() or None
    direct_url = str(meta.get("direct_url") or "").strip() or None
    return {
        "object_key": object_key,
        "direct_url": direct_url,
        "byte_size": meta.get("byte_size"),
        "content_type": meta.get("content_type"),
        "has_r2": bool(object_key),
    }


@router.get("/export")
def export_media_for_hub(
    db: Session = Depends(get_db),
    since_id: int = 0,
    limit: int | None = None,
    status: str = "approved",
    pool_id: int | None = None,
    origin: str | None = None,
    has_r2: bool | None = None,
):
    """Paginated ascending export for aof-forum ingest. Requires X-TBCC-Internal-Key when gate is on.

    origin=storage_hub — only Storage Hub topic rows and media in trusted AOF network pools
    (copies from /deposit and lane auto-pipe).

    has_r2=true — only rows already exported to R2 (classification_json.r2.object_key).
    Prefer object_key/direct_url over file_path when present (no Telethon download).
    """
    from app.models.media import Media
    from app.services.storage_hub_r2_export import media_has_r2

    since = max(int(since_id or 0), 0)
    page_limit = _clamp_export_limit(limit)
    q = db.query(Media).filter(Media.id > since)
    st = (status or "").strip().lower()
    if st:
        q = q.filter(Media.status == st)
    if pool_id is not None:
        q = q.filter(Media.pool_id == int(pool_id))
    origin_key = (origin or "").strip().lower()
    if origin_key == "storage_hub":
        q = _apply_storage_hub_export_filter(q, db)
    # Oversample when filtering has_r2 in Python (JSON shape varies).
    fetch_n = page_limit * 5 if has_r2 is not None else page_limit
    rows = q.order_by(Media.id.asc()).limit(fetch_n).all()
    if has_r2 is True:
        rows = [m for m in rows if media_has_r2(m)][:page_limit]
    elif has_r2 is False:
        rows = [m for m in rows if not media_has_r2(m)][:page_limit]
    else:
        rows = rows[:page_limit]
    items = []
    for m in rows:
        item = {
            "id": int(m.id),
            "source_channel": m.source_channel,
            "media_type": m.media_type,
            "telegram_message_id": m.telegram_message_id,
            "file_unique_id": m.file_unique_id,
            "tags": m.tags,
            "pool_id": m.pool_id,
            "pool_name": _pool_name_for_export_row(db, m.pool_id),
            "network_key": _network_key_for_export_row(db, m),
            "status": m.status,
            "file_path": f"/media/{int(m.id)}/file",
        }
        item.update(_r2_fields_for_export(m))
        items.append(item)
    next_since = int(rows[-1].id) if rows else since
    return {
        "items": items,
        "next_since_id": next_since,
        "count": len(items),
        "origin": origin_key or None,
    }


@router.post("/export/r2/tick")
def export_storage_hub_r2_tick(
    db: Session = Depends(get_db),
    since_id: int = 0,
    limit: int = 10,
    async_celery: bool = True,
):
    """Enqueue or run one Storage Hub → R2 export batch (internal key required)."""
    from app.services.storage_hub_r2_export import export_storage_hub_batch

    lim = _clamp_export_limit(limit)
    if async_celery:
        from app.workers.storage_hub_r2_export_worker import export_storage_hub_media_to_r2

        task = export_storage_hub_media_to_r2.delay(since_id=int(since_id or 0), limit=lim)
        return {"ok": True, "queued": True, "task_id": task.id, "since_id": since_id, "limit": lim}
    return export_storage_hub_batch(db, since_id=int(since_id or 0), limit=lim)


@router.get("/{media_id}")
def get_media(media_id: int, db: Session = Depends(get_db)):
    from app.models.media import Media
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        return {"error": "Not found"}
    return orm_to_dict(media)


_THUMB_BUSY_DETAIL = (
    "Thumbnail unavailable (Telegram session or database busy). "
    "Stop scraper_bot and other processes using admin.session, restart Celery worker, retry. "
    "See tbcc/docs/TELEGRAM_OPS.md"
)


def _load_thumbnail_ctx(media_id: int) -> MediaFetchContext | None:
    """Synchronous DB read for a thumbnail — run in a threadpool so cold cache misses
    never block the event loop (and never starve /pools or /media list)."""
    from app.models.media import Media

    db = SessionLocal()
    try:
        media = db.query(Media).filter(Media.id == media_id).first()
        if not media:
            return None
        return MediaFetchContext(
            id=int(media.id),
            source_channel=media.source_channel,
            telegram_message_id=media.telegram_message_id,
            media_type=media.media_type,
        )
    finally:
        db.close()


# Coalesce concurrent cache misses for the same id so one slow Telegram download is not
# started twice (each download holds the serialized admin session lock).
_THUMB_MISS_LOCKS: dict[int, asyncio.Lock] = {}


def _thumb_miss_lock(media_id: int) -> asyncio.Lock:
    lock = _THUMB_MISS_LOCKS.get(media_id)
    if lock is None:
        lock = asyncio.Lock()
        _THUMB_MISS_LOCKS[media_id] = lock
    return lock


def _thumbnail_file_response(path) -> FileResponse:
    # Served entirely from disk: no DB, no Telegram session, no SQLite connection.
    return FileResponse(
        str(path),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.post("/thumbnails/warm")
def warm_media_thumbnails(body: dict = Body(...)):
    """
    Queue Celery to download missing previews on the telegram worker (import session).
    Dashboard grids call this for the visible page — no Telethon on the API process.
    """
    from app.services.thumb_cache_service import queue_thumbnail_warm

    raw_ids = body.get("ids") if isinstance(body, dict) else None
    if not isinstance(raw_ids, list):
        raise HTTPException(status_code=400, detail="Expected JSON body { ids: number[] }")
    return queue_thumbnail_warm(raw_ids)


@router.get("/{media_id}/thumbnail")
async def get_media_thumbnail(
    media_id: int,
    refresh: bool = False,
    cache_only: bool = False,
):
    """
    Grid / preview thumbnail, served from a persistent on-disk cache.

    Cache hit  → static JPEG from disk (no DB, no Telegram). This is what keeps the
                 gallery solid while imports / sends / scraping / bulk approve run.
    Negative   → 404 (frontend shows a numeric placeholder); avoids re-hitting Telegram
                 every reload for posterless videos / failed fetches.
    Cold miss  → by default queues Celery warm (TBCC_THUMBNAIL_API_TELEGRAM=0); optional
                 inline Telegram fetch when TBCC_THUMBNAIL_API_TELEGRAM=1.
    """
    from app.services.media_cache_storage import (
        cached_thumb_path,
        clear_cached_thumb,
        negative_marker_fresh,
        write_negative_marker,
        write_thumb_atomic,
    )
    from app.services.telethon_thumb import NO_PREVIEW, fetch_thumbnail_bytes
    from app.services.thumb_cache_service import api_thumbnail_telegram_enabled, queue_thumbnail_warm

    if refresh:
        clear_cached_thumb(media_id)

    cached = cached_thumb_path(media_id)
    if cached is not None:
        return _thumbnail_file_response(cached)
    if cache_only:
        raise HTTPException(
            status_code=404,
            detail="Thumbnail not cached yet (cache_only mode — no Telegram fetch)",
        )
    if not refresh and negative_marker_fresh(media_id):
        raise HTTPException(status_code=404, detail="No preview available for this media")

    if not api_thumbnail_telegram_enabled():
        queue_thumbnail_warm([media_id])
        raise HTTPException(
            status_code=404,
            detail="Thumbnail warming — retry shortly",
            headers={"Retry-After": "3", "X-TBCC-Thumb-Warm": "1"},
        )

    async with _thumb_miss_lock(media_id):
        # Re-check: another request may have populated the cache while we waited.
        cached = cached_thumb_path(media_id)
        if cached is not None:
            return _thumbnail_file_response(cached)

        ctx = await run_in_threadpool(_load_thumbnail_ctx, media_id)
        if ctx is None:
            raise HTTPException(status_code=404, detail="Not found")

        try:
            result = await fetch_thumbnail_bytes(ctx)
        except HTTPException:
            raise

        if result is NO_PREVIEW:
            # Genuinely no preview (e.g. video with no poster frame). Remember it so we
            # stop asking Telegram on every gallery reload.
            write_negative_marker(media_id)
            raise HTTPException(status_code=404, detail="No preview available for this media")
        if result is None:
            # Transient busy / lock / timeout — do NOT negative-cache; let the next
            # reload retry once the session frees up.
            raise HTTPException(status_code=503, detail=_THUMB_BUSY_DETAIL, headers={"Retry-After": "5"})

        data, _mime = result
        # Store a real downscaled JPEG (cache files are .jpg / served as image/jpeg).
        jpeg = _image_bytes_to_thumbnail_jpeg(data)
        if jpeg:
            data = jpeg
        path = await run_in_threadpool(write_thumb_atomic, media_id, data)

    return _thumbnail_file_response(path)


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

    try:
        data, mime = await asyncio.wait_for(_fetch_media_bytes_and_type(ctx), timeout=120.0)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Telegram download timed out. Retry when Celery queue is shorter.",
        )
    except HTTPException:
        raise
    except Exception as e:
        msg = str(e).lower()
        if "database is locked" in msg or "sqlite_busy" in msg:
            raise HTTPException(status_code=503, detail=_THUMB_BUSY_DETAIL)
        raise
    if mime == "application/octet-stream":
        kind, ext = sniff_media_kind(data)
        mime = _MIME_FROM_EXT.get(ext, mime)
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
                fid = _norm_media_fid(media.file_unique_id)
                if fid:
                    conflict = (
                        db.query(Media)
                        .filter(
                            Media.pool_id == pid,
                            Media.file_unique_id == media.file_unique_id,
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
    from app.services.media_cache_storage import clear_cached_thumb

    clear_cached_thumb(media_id)
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
    target_fids = {_norm_media_fid(r[0]) for r in target_fid_rows if _norm_media_fid(r[0])}

    seen_batch_fids: set[str] = set()
    seen_batch_empty = False
    target_has_empty = (
        db.query(Media.id)
        .filter(
            Media.pool_id == pid,
            Media.id.notin_(id_list),
            or_(Media.file_unique_id.is_(None), Media.file_unique_id == ""),
        )
        .first()
        is not None
    )
    skipped_dup = 0
    to_move: list[int] = []

    for mid_int in id_list:
        m = medias.get(mid_int)
        if not m:
            continue
        fid = _norm_media_fid(m.file_unique_id)
        if fid:
            if fid in target_fids or fid in seen_batch_fids:
                skipped_dup += 1
                continue
            seen_batch_fids.add(fid)
        else:
            if target_has_empty or seen_batch_empty:
                skipped_dup += 1
                continue
            seen_batch_empty = True
        to_move.append(mid_int)

    updated = 0
    if to_move:
        try:
            stmt = update(Media).where(Media.id.in_(to_move)).values(pool_id=pid)
            result = db.execute(stmt)
            db.commit()
            updated = int(result.rowcount or 0)
        except IntegrityError as exc:
            db.rollback()
            logger.warning(
                "bulk_move_pool bulk UPDATE hit dedup constraint pool_id=%s ids=%s: %s",
                pid,
                len(to_move),
                exc.orig if getattr(exc, "orig", None) else exc,
            )
            for mid_int in to_move:
                m = medias.get(mid_int)
                if not m:
                    continue
                fid = _norm_media_fid(m.file_unique_id)
                if fid:
                    conflict = (
                        db.query(Media.id)
                        .filter(
                            Media.pool_id == pid,
                            Media.file_unique_id == m.file_unique_id,
                            Media.id != mid_int,
                        )
                        .first()
                    )
                    if conflict:
                        skipped_dup += 1
                        continue
                else:
                    conflict = (
                        db.query(Media.id)
                        .filter(
                            Media.pool_id == pid,
                            Media.id != mid_int,
                            (Media.file_unique_id.is_(None)) | (Media.file_unique_id == ""),
                        )
                        .first()
                    )
                    if conflict:
                        skipped_dup += 1
                        continue
                try:
                    m.pool_id = pid
                    db.flush()
                    updated += 1
                except IntegrityError:
                    db.rollback()
                    skipped_dup += 1
            db.commit()

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


@router.patch("/bulk/gallery-capture-meta")
def bulk_gallery_capture_meta(data: dict = Body(...), db: Session = Depends(get_db)):
    """
    Merge admin-only capture metadata into media.classification_json under tbcc_gallery_capture
    (source page hostname — not shown in Telegram captions; extension auto-tag uses this instead of a site #hashtag).
    """
    from app.models.media import Media

    ids = data.get("ids") or []
    site_host = str(data.get("site_host") or "").strip() or None
    source_page = str(data.get("source_page") or "").strip() or None
    if site_host:
        site_host = site_host[:255]
    if source_page:
        source_page = source_page[:2048]
    patch: dict = {}
    if site_host:
        patch["site_host"] = site_host
    if source_page:
        patch["source_page"] = source_page
    if not ids or not patch:
        return {"updated": 0, "error": None if not ids else "Need site_host and/or source_page"}
    n = 0
    for mid in ids:
        try:
            mid_int = int(mid)
        except (TypeError, ValueError):
            continue
        m = db.query(Media).filter(Media.id == mid_int).first()
        if not m:
            continue
        meta: dict = {}
        raw = getattr(m, "classification_json", None)
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    meta = parsed
            except Exception:
                meta = {}
        prev_gc = meta.get("tbcc_gallery_capture")
        if not isinstance(prev_gc, dict):
            prev_gc = {}
        prev_gc.update(patch)
        meta["tbcc_gallery_capture"] = prev_gc
        m.classification_json = json.dumps(meta, ensure_ascii=False)
        n += 1
    db.commit()
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
