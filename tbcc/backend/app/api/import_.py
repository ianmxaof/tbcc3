import asyncio
import logging
import os
from typing import Annotated
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.database.session import get_db
from app.services.telegram_admin import get_telegram_storage, import_lock
from app.services.hls_import import hls_or_dash_url_to_mp4_bytes
from app.services.media_sniff import maybe_remux_mp4_for_playback, sniff_media_kind, telegram_media_type_from_sniff
from app.services.tbcc_media_url import sanitize_import_source_url
from telethon.errors.rpcerrorlist import ImageProcessFailedError

router = APIRouter()

SAVED_BATCH_MAX_FILES = 100


class HlsManifestUrlBody(BaseModel):
    """HLS (.m3u8) or DASH (.mpd) manifest URL — server runs ffmpeg to produce one MP4 (requires ffmpeg on PATH)."""

    url: str = Field(..., min_length=12, max_length=8000)
    pool_id: int = 1
    saved_only: bool = False
    referer: str | None = Field(default=None, description="Optional Referer for ffmpeg HTTP requests")
    source: str = Field(default="import:hls-url", max_length=200)


class SavedBatchUrlsBody(BaseModel):
    """Ordered list of http(s) URLs to download and send to Saved Messages as albums (≤10 per album)."""

    urls: list[str] = Field(..., min_length=1, max_length=SAVED_BATCH_MAX_FILES)
    caption: str | None = Field(default=None, description="Caption on each album (Saved Messages)")


def _guess_media_type_from_content_type(content_type: str | None) -> str:
    """Guess media type from Content-Type header only (for bytes upload)."""
    if content_type:
        if "image" in content_type or "gif" in content_type:
            return "photo"
        if "video" in content_type:
            return "video"
    return "photo"


def _guess_media_type(url: str, content_type: str | None) -> str:
    if content_type:
        if "image" in content_type:
            return "photo"
        if "video" in content_type:
            return "video"
        if "gif" in content_type:
            return "photo"
    url_lower = url.lower()
    path = url_lower.split("?", 1)[0]
    if any(path.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
        return "photo"
    if path.endswith(".gif"):
        return "photo"
    if any(path.endswith(ext) for ext in (".mp4", ".webm", ".mov", ".m4v", ".mkv")):
        return "video"
    return "photo"


def _refine_media_type_from_bytes(file_bytes: bytes, guess: str) -> str:
    """Use magic bytes so we never upload GIF/WebP as fake .mp4."""
    kind, _ = sniff_media_kind(file_bytes)
    if kind != "document":
        return telegram_media_type_from_sniff(kind)
    g = (guess or "photo").lower()
    return g if g in ("photo", "video", "document") else "photo"


_MEDIA_EXTS = (".mp4", ".webm", ".mov", ".m4v", ".mkv", ".jpg", ".jpeg", ".png", ".gif", ".webp")


def _headers_with_referer(referer: str) -> dict[str, str]:
    h: dict[str, str] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referer,
    }
    if "erome.com" in referer:
        h["Origin"] = "https://www.erome.com"
    return h


def _erome_referrer_chain(url: str) -> list[str]:
    """Erome CDN expects Referer from the album page /a/{albumId}, not the CDN hostname."""
    out: list[str] = []
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        if not (host == "erome.com" or host.endswith(".erome.com")):
            return []
        parts = [x for x in p.path.split("/") if x]
        if len(parts) >= 2:
            last = parts[-1].lower()
            if any(last.endswith(ext) for ext in _MEDIA_EXTS):
                album = parts[-2]
                if album.isdigit() and len(parts) >= 3:
                    album = parts[-3]
                if album and not album.isdigit():
                    out.append(f"https://www.erome.com/a/{album}")
        out.append("https://www.erome.com/")
        seen: set[str] = set()
        unique: list[str] = []
        for x in out:
            if x not in seen:
                seen.add(x)
                unique.append(x)
        return unique
    except Exception:
        return ["https://www.erome.com/"]


def _browser_like_headers(url: str) -> dict[str, str]:
    referer = ""
    try:
        p = urlparse(url)
        if p.scheme and p.netloc:
            referer = f"{p.scheme}://{p.netloc}/"
    except Exception:
        pass
    return _headers_with_referer(referer or "https://www.erome.com/")


async def _httpx_get_media(url: str, timeout: float) -> tuple[bytes, str]:
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
    except Exception:
        host = ""
    async with httpx.AsyncClient() as client:
        if host == "erome.com" or host.endswith(".erome.com"):
            last_err: BaseException | None = None
            for ref in _erome_referrer_chain(url):
                try:
                    r = await client.get(
                        url,
                        follow_redirects=True,
                        timeout=timeout,
                        headers=_headers_with_referer(ref),
                    )
                    r.raise_for_status()
                    return r.content, r.headers.get("content-type", "")
                except httpx.HTTPError as e:
                    last_err = e
                    logger.debug("erome fetch referer=%s failed: %s", ref, e)
            if last_err:
                raise last_err
            raise RuntimeError("Erome fetch failed")
        r = await client.get(
            url,
            follow_redirects=True,
            timeout=timeout,
            headers=_browser_like_headers(url),
        )
        r.raise_for_status()
        return r.content, r.headers.get("content-type", "")


def _caption_from_body(data: dict | None) -> str | None:
    if not data:
        return None
    c = data.get("caption")
    if isinstance(c, str):
        s = c.strip()
        return s or None
    return None


async def _import_saved_batch_urls_impl(urls: list[str], caption: str | None = None) -> dict:
    """
    Download multiple URLs server-side and send to Saved Messages as albums (≤10 per album).
    Shared by POST /import/saved-batch-urls and POST /import/url (urls[] + saved_only).
    """
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        return {"error": "Telegram API not configured"}

    for u in urls:
        u = (u or "").strip()
        if not u.startswith("http://") and not u.startswith("https://"):
            return {"error": f"Invalid URL: {u[:80]}"}

    items: list[tuple[bytes, str]] = []
    for url in urls:
        url = url.strip()
        url_l = url.lower()
        is_large_media = any(url_l.split("?", 1)[0].endswith(ext) for ext in (".mp4", ".webm", ".mov", ".m4v", ".mkv"))
        timeout = 300.0 if is_large_media else 60.0
        try:
            file_bytes, content_type = await _httpx_get_media(url, timeout)
        except httpx.HTTPError as e:
            logger.warning("saved-batch-urls fetch failed url=%s err=%s", url[:80], e)
            return {"error": f"Could not download URL ({e})"}

        file_bytes = await asyncio.to_thread(maybe_remux_mp4_for_playback, file_bytes)
        media_type = _guess_media_type(url, content_type)
        media_type = _refine_media_type_from_bytes(file_bytes, media_type)
        items.append((file_bytes, media_type))

    async with import_lock():
        storage = await get_telegram_storage()
        try:
            await storage.save_batch_to_saved_only(items, caption=caption)
        except ImageProcessFailedError as e:
            logger.warning("Telegram rejected saved-batch-urls err=%s", e)
            return {"error": f"Telegram rejected batch (corrupt or unsupported): {e}"}

    return {
        "status": "saved_only",
        "message": "Saved to Telegram Saved Messages (grouped into albums of up to 10)",
        "count": len(items),
    }


@router.post("/url")
async def import_from_url(data: dict, db: Session = Depends(get_db)):
    """Single URL import, or batch Saved Messages when body includes urls[] + saved_only (same as /saved-batch-urls)."""
    urls_batch = data.get("urls")
    if isinstance(urls_batch, list) and len(urls_batch) > 0:
        if data.get("saved_only") is not True:
            return {"error": "urls array requires saved_only: true"}
        try:
            validated = SavedBatchUrlsBody(urls=urls_batch)
        except ValidationError as e:
            return {"error": f"Invalid urls: {e}"}
        return await _import_saved_batch_urls_impl(validated.urls, caption=_caption_from_body(data))

    url = data.get("url")
    pool_id = data.get("pool_id", 1)
    saved_only = data.get("saved_only") is True

    if not url:
        return {"error": "No URL provided"}
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        return {"error": "Telegram API not configured"}

    url_l = url.lower()
    is_large_media = any(url_l.split("?", 1)[0].endswith(ext) for ext in (".mp4", ".webm", ".mov", ".m4v", ".mkv"))
    timeout = 300.0 if is_large_media else 60.0
    try:
        file_bytes, content_type = await _httpx_get_media(url, timeout)
    except httpx.HTTPError as e:
        logger.warning("import/url fetch failed url=%s err=%s", url[:80], e)
        return {"error": f"Could not download URL ({e})"}

    file_bytes = await asyncio.to_thread(maybe_remux_mp4_for_playback, file_bytes)
    media_type = _guess_media_type(url, content_type)
    cap = _caption_from_body(data)
    async with import_lock():
        storage = await get_telegram_storage()
        if saved_only:
            await storage.save_to_saved_only(file_bytes, media_type, caption=cap)
            return {"status": "saved_only", "message": "Saved to Telegram Saved Messages"}
        record = await storage.store_from_bytes(file_bytes, media_type, sanitize_import_source_url(url), pool_id, db)
        if record:
            logger.info("Imported media id=%s pool_id=%s", record.id, pool_id)
            return {"status": "imported", "media_id": record.id}
        logger.warning("Import skipped (duplicate or unsupported format) url=%s", url[:80])
        return {"status": "skipped", "reason": "duplicate or unsupported format", "media_id": None}


@router.post("/bytes")
async def import_from_bytes(
    file: UploadFile = File(...),
    pool_id: int = Form(1),
    saved_only: bool = Form(False),
    source: str = Form("extension:bytes"),
    caption: str = Form(""),
    db: Session = Depends(get_db),
):
    """
    Import media from raw bytes (e.g. from extension after in-page fetch).
    Use this to bypass protected sites that block direct URL downloads
    (OnlyFans, FetLife, etc.): extension fetches in page context and POSTs here.
    """
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        return {"error": "Telegram API not configured"}

    file_bytes = await file.read()
    if not file_bytes:
        return {"error": "Empty file"}

    file_bytes = await asyncio.to_thread(maybe_remux_mp4_for_playback, file_bytes)

    content_type = file.content_type or ""
    fn = (file.filename or "").lower()
    if any(fn.endswith(ext) for ext in (".mp4", ".webm", ".mov", ".m4v", ".mkv")):
        media_type = "video"
    elif fn.endswith(".gif") or fn.endswith(".png") or fn.endswith(".webp"):
        media_type = "photo"
    elif "video" in content_type or "webm" in content_type:
        media_type = "video"
    else:
        media_type = _guess_media_type_from_content_type(content_type)

    media_type = _refine_media_type_from_bytes(file_bytes, media_type)
    cap = (caption or "").strip() or None

    async with import_lock():
        storage = await get_telegram_storage()
        try:
            if saved_only:
                await storage.save_to_saved_only(file_bytes, media_type, caption=cap)
                return {"status": "saved_only", "message": "Saved to Telegram Saved Messages"}
            record = await storage.store_from_bytes(file_bytes, media_type, sanitize_import_source_url(source), pool_id, db)
            if record:
                logger.info("Imported media id=%s pool_id=%s (bytes upload)", record.id, pool_id)
                return {"status": "imported", "media_id": record.id}
            return {"status": "skipped", "reason": "duplicate or unsupported format", "media_id": None}
        except ImageProcessFailedError as e:
            logger.warning("Telegram rejected bytes import err=%s", e)
            return {"error": f"Telegram rejected this file (corrupt or unsupported): {e}"}


@router.post("/hls-url")
async def import_hls_manifest_url(body: HlsManifestUrlBody, db: Session = Depends(get_db)):
    """
    Download muxed video from an HLS (.m3u8) or DASH (.mpd) manifest using ffmpeg.
    Requires ffmpeg on the server PATH. DRM-protected streams will fail.
    """
    if os.environ.get("TBCC_DISABLE_HLS_IMPORT", "").strip().lower() in ("1", "true", "yes"):
        return {"error": "HLS import disabled (TBCC_DISABLE_HLS_IMPORT)"}
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        return {"error": "Telegram API not configured"}
    url = (body.url or "").strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        return {"error": "Invalid URL"}
    try:
        ref = body.referer
        if not ref:
            try:
                p = urlparse(url)
                if p.scheme and p.netloc:
                    ref = f"{p.scheme}://{p.netloc}/"
            except Exception:
                ref = None
        file_bytes = await asyncio.to_thread(lambda: hls_or_dash_url_to_mp4_bytes(url, referer=ref))
    except Exception as e:
        logger.warning("hls-url import failed: %s", e)
        return {"error": str(e)}

    file_bytes = await asyncio.to_thread(maybe_remux_mp4_for_playback, file_bytes)
    media_type = _refine_media_type_from_bytes(file_bytes, "video")
    src = sanitize_import_source_url(body.source or "import:hls-url")
    async with import_lock():
        storage = await get_telegram_storage()
        try:
            if body.saved_only:
                await storage.save_to_saved_only(file_bytes, media_type, caption=None)
                return {"status": "saved_only", "message": "Saved to Telegram Saved Messages"}
            record = await storage.store_from_bytes(file_bytes, media_type, src, body.pool_id, db)
            if record:
                logger.info("Imported HLS media id=%s pool_id=%s", record.id, body.pool_id)
                return {"status": "imported", "media_id": record.id}
            return {"status": "skipped", "reason": "duplicate or unsupported format", "media_id": None}
        except ImageProcessFailedError as e:
            logger.warning("Telegram rejected HLS import err=%s", e)
            return {"error": f"Telegram rejected this file: {e}"}


@router.post("/saved-batch")
async def import_saved_batch(
    files: Annotated[list[UploadFile], File(description="Repeat field name 'files' for each part")],
    caption: str = Form(""),
):
    """
    Send multiple uploads to Saved Messages as Telegram albums (max 10 media per album).
    Order is preserved; photo vs video are grouped into separate consecutive albums.
    """
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        return {"error": "Telegram API not configured"}
    if not files or len(files) > SAVED_BATCH_MAX_FILES:
        return {"error": f"Provide 1–{SAVED_BATCH_MAX_FILES} files"}
    logger.info("saved-batch: received %s file part(s)", len(files))

    items: list[tuple[bytes, str]] = []
    for uf in files:
        raw = await uf.read()
        if not raw:
            continue
        raw = await asyncio.to_thread(maybe_remux_mp4_for_playback, raw)
        content_type = uf.content_type or ""
        fn = (uf.filename or "").lower()
        if any(fn.endswith(ext) for ext in (".mp4", ".webm", ".mov", ".m4v", ".mkv")):
            guess = "video"
        elif fn.endswith(".gif") or fn.endswith(".png") or fn.endswith(".webp"):
            guess = "photo"
        elif "video" in content_type or "webm" in content_type:
            guess = "video"
        else:
            guess = _guess_media_type_from_content_type(content_type)
        media_type = _refine_media_type_from_bytes(raw, guess)
        items.append((raw, media_type))

    if not items:
        return {"error": "No usable file bytes"}

    cap = (caption or "").strip() or None
    async with import_lock():
        storage = await get_telegram_storage()
        try:
            await storage.save_batch_to_saved_only(items, caption=cap)
        except ImageProcessFailedError as e:
            logger.warning("Telegram rejected saved-batch err=%s", e)
            return {"error": f"Telegram rejected batch (corrupt or unsupported): {e}"}

    return {
        "status": "saved_only",
        "message": "Saved to Telegram Saved Messages (grouped into albums of up to 10)",
        "count": len(items),
    }


@router.post("/saved-batch-urls")
async def import_saved_batch_urls(body: SavedBatchUrlsBody):
    """Alias for batch Saved Messages (albums). Prefer POST /import/url with urls[] if this route is missing (older servers)."""
    cap = body.caption.strip() if body.caption else None
    return await _import_saved_batch_urls_impl(body.urls, caption=cap)


@router.post("/from-saved")
async def import_from_saved_messages(data: dict, db: Session = Depends(get_db)):
    """
    Index media already in Telegram Saved Messages into a content pool (no re-upload).
    Uses the admin Telethon session (same account as extension/dashboard imports).
    Body: pool_id (int), limit (optional, default 50, max 200), source (optional label for Media.source_channel).
    """
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        return {"error": "Telegram API not configured"}
    try:
        pool_id = int(data.get("pool_id") or 1)
    except (TypeError, ValueError):
        return {"error": "Invalid pool_id"}
    try:
        limit = int(data.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    limit = min(max(limit, 1), 200)
    source = (data.get("source") or "telegram:saved_messages").strip() or "telegram:saved_messages"

    async with import_lock():
        storage = await get_telegram_storage()
        try:
            result = await storage.index_from_saved_messages(pool_id, source, db, limit=limit)
        except Exception as e:
            logger.exception("import/from-saved failed: %s", e)
            return {"error": str(e)}
    return {"status": "ok", **result}
