import asyncio
import errno
import json
import logging
import os
from typing import Annotated
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.database.session import get_db
from app.services.image_crop_pipeline import ImageCropSettings, apply_image_crop_pipeline
from app.schemas.watermark_options import WatermarkOptions
from app.services.media_watermark import (
    maybe_apply_media_watermark,
    skip_watermark_context,
    watermark_config_context,
    watermark_config_public,
)
from app.services.watermark_settings_effective import build_apply_config
from app.services.telegram_admin import (
    friendly_telegram_error,
    run_telegram_album_composer_io,
    run_telegram_import_io,
    run_telegram_io,
)
from app.services.hls_import import hls_or_dash_url_to_mp4_bytes
from app.services.media_sniff import maybe_remux_mp4_for_playback, sniff_media_kind, telegram_media_type_from_sniff
from app.services.tbcc_media_url import sanitize_import_source_url
from telethon.errors.rpcerrorlist import ImageProcessFailedError

router = APIRouter()

from app.api import import_jobs as import_jobs_api  # noqa: E402

router.include_router(import_jobs_api.router)

SAVED_BATCH_MAX_FILES = 100


async def _import_bytes_to_pool(
    file_bytes: bytes,
    media_type: str,
    source: str,
    pool_id: int,
    db: Session,
    *,
    skip_watermark: bool = False,
):
    """Pool import: local disk by default; legacy Saved Messages upload when TBCC_POOL_IMPORT_LOCAL=0."""
    from app.services.local_media_storage import pool_import_local_enabled, store_pool_media_from_bytes

    if pool_import_local_enabled():
        return store_pool_media_from_bytes(
            file_bytes,
            media_type,
            source,
            pool_id,
            db,
            skip_watermark=skip_watermark,
        )

    async def _store(storage):
        return await storage.store_from_bytes(
            file_bytes, media_type, source, pool_id, db, skip_watermark=skip_watermark
        )

    return await run_telegram_import_io(_store)


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
    append_send_promo: bool = Field(default=False, description="Append active gallery send-promo as last album image")


class SavedFromBotFileItem(BaseModel):
    file_id: str = Field(..., min_length=1, max_length=512)
    kind: str = Field(default="photo", description="photo or video")


class SavedFromBotMessagesBody(BaseModel):
    """Instant send: Telethon server-side copy from album bot DM (no byte download)."""

    media_count: int = Field(..., ge=1, le=SAVED_BATCH_MAX_FILES)
    message_ids: list[int] = Field(default_factory=list, max_length=SAVED_BATCH_MAX_FILES)
    anchor_max_message_id: int | None = Field(
        default=None, description="Newest message id in batch (scopes bot chat scan)"
    )
    bot_username: str = Field(..., min_length=1, max_length=128, description="Album bot @username without @")
    caption: str | None = Field(default=None, description="Caption on each album chunk")
    append_send_promo: bool = Field(default=False, description="Append active gallery send-promo to last photo album")
    files: list[SavedFromBotFileItem] = Field(
        default_factory=list,
        max_length=SAVED_BATCH_MAX_FILES,
        description="Bot API file_id fallback when Telethon message lookup fails",
    )
    crop: ImageCropSettings | None = Field(
        default=None,
        description="Percent inset / blur bands (photos only; uses file download path)",
    )
    watermark: WatermarkOptions | None = Field(
        default=None,
        description="Promo text burn-in (uses byte download path when enabled)",
    )


def _import_uncaught_error(exc: BaseException, *, endpoint: str) -> dict:
    """Return JSON error body instead of letting import endpoints 500."""
    from sqlalchemy.exc import SQLAlchemyError

    logger.warning("%s uncaught err=%s", endpoint, exc, exc_info=True)
    if isinstance(exc, SQLAlchemyError):
        return {
            "error": (
                "Database error during import — retry in a few seconds. "
                "If this persists, run alembic upgrade head and restart TBCC-Backend."
            )
        }
    if isinstance(exc, (OSError, PermissionError)):
        return {"error": f"Local storage error during import: {exc}"}
    try:
        return {"error": friendly_telegram_error(exc)}
    except Exception:
        return {"error": f"Import failed: {str(exc)[:300]}"}


def _watermark_should_apply(
    db: Session,
    wm: WatermarkOptions | None,
    *,
    context: str = "default",
) -> bool:
    if wm and wm.skip:
        return False
    if wm and wm.enabled is False:
        return False
    if context == "erome":
        from app.services.erome_promo_wire import erome_watermark_required
        from app.services.watermark_settings_effective import build_apply_config

        if not erome_watermark_required():
            return False
        cfg = build_apply_config(db, override=wm)
        return bool(cfg.enabled and cfg.texts)
    from app.services.watermark_settings_effective import get_effective_watermark_settings

    effective = get_effective_watermark_settings(db)
    if context == "album_composer" and not effective.get("apply_on_album_composer"):
        if wm is None or wm.enabled is None:
            return False
    if context == "saved_import" and not effective.get("apply_on_saved_import"):
        if wm is None or wm.enabled is None:
            return False
    cfg = build_apply_config(db, override=wm)
    return bool(cfg.enabled and cfg.texts)


def _process_media_bytes(
    data: bytes,
    kind: str,
    db: Session,
    *,
    crop: ImageCropSettings | None = None,
    wm: WatermarkOptions | None = None,
    context: str = "default",
) -> bytes:
    if kind == "photo" and crop and crop.applies():
        data = apply_image_crop_pipeline(data, crop)
    if _watermark_should_apply(db, wm, context=context):
        cfg = build_apply_config(db, override=wm)
        with watermark_config_context(cfg):
            data = maybe_apply_media_watermark(data, kind, config=cfg)
    return data


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
                if album:
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


def _transient_network_failure(exc: BaseException) -> bool:
    """DNS blips, refused sockets, timeouts — safe to retry a few times."""
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.WriteError)):
        return True
    if isinstance(exc, httpx.CloseError):
        return True
    e: BaseException | None = exc
    for _ in range(10):
        if isinstance(e, OSError):
            code = getattr(e, "winerror", None) or getattr(e, "errno", None)
            if code in (
                11001,
                11002,
                10060,
                10061,
                10051,
                errno.EAGAIN,
                errno.ECONNRESET,
                errno.ETIMEDOUT,
                errno.ECONNREFUSED,
                errno.EHOSTUNREACH,
                errno.ENETUNREACH,
            ):
                return True
        msg = str(e).lower()
        if (
            "getaddrinfo" in msg
            or "name or service not known" in msg
            or "temporary failure in name resolution" in msg
            or "nodename nor servname" in msg
        ):
            return True
        e = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
    return False


def _friendly_download_error(url: str, exc: BaseException) -> str:
    """Short, actionable message for API clients (avoid raw errno dumps in UI)."""
    host = ""
    try:
        host = (urlparse(url).hostname or "").strip()
    except Exception:
        pass
    raw = str(exc).strip()
    low = raw.lower()
    if "getaddrinfo" in low or "11001" in raw or "name or service not known" in low or "nodename nor servname" in low:
        return (
            "Could not resolve host (DNS). "
            + (f"Host: {host}. " if host else "")
            + "Check the URL, your network, and that the machine running TBCC can reach the internet."
        )
    if "certificate" in low or "ssl" in low or "tls" in low:
        return f"TLS/SSL error while downloading{f' ({host})' if host else ''}: {raw[:180]}"
    if "timed out" in low or "timeout" in low:
        return (
            "Download timed out"
            + (f" for {host}" if host else "")
            + ". Try again, use a smaller file, or fetch via the extension session for protected CDNs."
        )
    if "403" in raw or "forbidden" in low:
        return f"HTTP forbidden (403){f' — {host}' if host else ''}. This host may require cookies; use session import from the gallery."
    if "404" in raw or "not found" in low:
        return f"Not found (404){f' — {host}' if host else ''}."
    return f"Could not download: {raw[:220]}"


async def _httpx_get_media_attempt(url: str, timeout: float) -> tuple[bytes, str]:
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


def _reject_non_media_payload(file_bytes: bytes, *, url: str = "") -> None:
    from app.services.media_sniff import reject_html_or_tiny_payload

    reject_html_or_tiny_payload(file_bytes, url=url)


async def _httpx_get_media(url: str, timeout: float) -> tuple[bytes, str]:
    delays_s = (0.0, 0.75, 2.25)
    last_exc: BaseException | None = None
    for attempt, delay in enumerate(delays_s):
        if delay:
            await asyncio.sleep(delay)
        try:
            return await _httpx_get_media_attempt(url, timeout)
        except Exception as e:
            last_exc = e
            if attempt + 1 < len(delays_s) and _transient_network_failure(e):
                logger.info(
                    "import fetch retry %s/%s url=%s err=%s",
                    attempt + 1,
                    len(delays_s),
                    url[:120],
                    e,
                )
                continue
            raise
    assert last_exc is not None
    raise last_exc


def _caption_from_body(data: dict | None) -> str | None:
    if not data:
        return None
    c = data.get("caption")
    if isinstance(c, str):
        s = c.strip()
        return s or None
    return None


def _truthy_flag(value) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def _gallery_send_promo_item(db: Session) -> tuple[bytes, str] | None:
    from app.services.gallery_send_promo import load_active_send_promo_bytes

    return load_active_send_promo_bytes(db)


def _album_composer_bot_token() -> str | None:
    token = (os.getenv("TBCC_ALBUM_COMPOSER_BOT_TOKEN") or "").strip()
    return token or None


def _album_composer_bot_user_id() -> int | None:
    token = _album_composer_bot_token()
    if not token or ":" not in token:
        return None
    try:
        return int(token.split(":", 1)[0])
    except ValueError:
        return None


def _exc_detail(exc: BaseException) -> str:
    text = str(exc).strip()
    if text:
        return text
    return type(exc).__name__


async def _download_bot_api_file(file_id: str, token: str) -> bytes:
    base = f"https://api.telegram.org/bot{token}"
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=15.0, read=120.0, write=60.0, pool=10.0)) as client:
        meta = await client.get(f"{base}/getFile", params={"file_id": file_id})
        payload: dict = {}
        try:
            payload = meta.json()
        except Exception:
            payload = {}
        if not meta.is_success or not payload.get("ok"):
            desc = str(payload.get("description") or meta.text or meta.reason_phrase or "getFile failed")
            low = desc.lower()
            if meta.status_code == 400 or "wrong file" in low or "file_id" in low:
                raise ValueError(
                    "Telegram file_id is invalid or expired — re-send photos/videos to the album bot, "
                    f"then post again. ({desc})"
                )
            meta.raise_for_status()
            raise ValueError(desc)
        path = str(payload["result"]["file_path"])
        blob = await client.get(f"https://api.telegram.org/file/bot{token}/{path}")
        blob.raise_for_status()
        return blob.content


async def _download_album_bot_processed_bytes(
    *,
    bot_peer: str,
    media_count: int,
    message_ids: list[int] | None,
    anchor_max_message_id: int | None,
    files: list[SavedFromBotFileItem] | None,
    db: Session,
    crop: ImageCropSettings | None = None,
    wm: WatermarkOptions | None = None,
    context: str = "album_composer",
) -> list[tuple[bytes, str]]:
    """
    Download staged album-bot media for watermark/crop pipeline.
    Prefer Telethon (handles large videos); fall back to Bot API file_id when needed.
    """
    msg_ids = [int(i) for i in (message_ids or []) if i]
    file_items = list(files or [])
    token = _album_composer_bot_token()

    async def _telethon_bytes(storage):
        items = await storage.download_bot_batch_bytes(
            bot_peer,
            media_count,
            message_ids=msg_ids or None,
            anchor_max_message_id=anchor_max_message_id,
        )
        return [
            (_process_media_bytes(data, kind, db, crop=crop, wm=wm, context=context), kind) for data, kind in items
        ]

    telethon_err: BaseException | None = None
    try:
        processed = await run_telegram_album_composer_io(_telethon_bytes)
        if len(processed) >= media_count:
            return processed[:media_count]
        telethon_err = ValueError(
            f"Telethon returned {len(processed)}/{media_count} item(s) from album bot chat"
        )
    except Exception as e:
        telethon_err = e
        logger.warning(
            "album bot Telethon byte download failed (count=%s ids=%s anchor=%s): %s",
            media_count,
            msg_ids[:8],
            anchor_max_message_id,
            _exc_detail(e),
        )

    if not file_items:
        if telethon_err is not None:
            raise telethon_err
        raise ValueError(
            "No staged media found in the album bot chat. Re-send photos/videos to the bot, then post again."
        )

    if not token:
        raise ValueError("TBCC_ALBUM_COMPOSER_BOT_TOKEN not set in tbcc/.env")

    logger.info(
        "album bot Telethon download incomplete (%s); trying Bot API file_id fallback for %s file(s)",
        _exc_detail(telethon_err) if telethon_err else "unknown",
        len(file_items),
    )

    processed: list[tuple[bytes, str]] = []
    for fi in file_items[:media_count]:
        data = await _download_bot_api_file(fi.file_id, token)
        kind = (fi.kind or "photo").lower()
        if kind not in ("photo", "video"):
            kind = "photo"
        processed.append((_process_media_bytes(data, kind, db, crop=crop, wm=wm), kind))

    if len(processed) < media_count:
        raise ValueError(
            f"Downloaded {len(processed)}/{media_count} item(s) via Bot API. "
            "Large videos require Telethon — re-send to the bot and retry, or check admin_album.session login."
        )
    return processed


async def _saved_batch_from_bot_files(
    files: list[SavedFromBotFileItem],
    caption: str | None,
    append_send_promo: bool,
    db: Session,
    *,
    use_album_session: bool = False,
    crop: ImageCropSettings | None = None,
    wm: WatermarkOptions | None = None,
) -> dict:
    token = _album_composer_bot_token()
    if not token:
        return {"error": "TBCC_ALBUM_COMPOSER_BOT_TOKEN not set in tbcc/.env"}

    async def _one(item: SavedFromBotFileItem) -> tuple[bytes, str]:
        data = await _download_bot_api_file(item.file_id, token)
        kind = (item.kind or "photo").lower()
        if kind not in ("photo", "video"):
            kind = "photo"
        data = _process_media_bytes(data, kind, db, crop=crop, wm=wm)
        return data, kind

    try:
        items = await asyncio.gather(*[_one(f) for f in files])
    except Exception as e:
        logger.warning("bot API file download failed: %s", e)
        return {"error": f"Could not download from album bot: {_exc_detail(e)}"}

    promo_item = _gallery_send_promo_item(db) if append_send_promo else None
    cap = (caption or "").strip() or None
    io_fn = run_telegram_album_composer_io if use_album_session else run_telegram_import_io
    try:
        await io_fn(
            lambda storage: storage.save_batch_to_saved_only(items, caption=cap, promo_item=promo_item)
        )
    except ImageProcessFailedError as e:
        return {"error": f"Telegram rejected batch: {e}"}
    except Exception as e:
        return {"error": friendly_telegram_error(e)}

    return {
        "status": "saved_only",
        "message": "Saved to Telegram Saved Messages (via bot file download)",
        "count": len(items),
    }


async def _import_saved_batch_urls_impl(
    urls: list[str],
    caption: str | None = None,
    *,
    append_send_promo: bool = False,
    db: Session | None = None,
) -> dict:
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
    ok_urls: list[str] = []
    url_errors: list[dict[str, str]] = []
    for url in urls:
        url = url.strip()
        url_l = url.lower()
        is_large_media = any(url_l.split("?", 1)[0].endswith(ext) for ext in (".mp4", ".webm", ".mov", ".m4v", ".mkv"))
        timeout = 300.0 if is_large_media else 60.0
        try:
            file_bytes, content_type = await _httpx_get_media(url, timeout)
            file_bytes = await asyncio.to_thread(maybe_remux_mp4_for_playback, file_bytes)
            media_type = _guess_media_type(url, content_type)
            media_type = _refine_media_type_from_bytes(file_bytes, media_type)
            items.append((file_bytes, media_type))
            ok_urls.append(url)
        except Exception as e:
            friendly = _friendly_download_error(url, e)
            logger.warning("saved-batch-urls fetch failed url=%s err=%s", url[:120], e)
            url_errors.append({"url": url[:800], "error": friendly})

    if not items:
        if len(url_errors) == 1:
            return {"error": url_errors[0]["error"]}
        return {
            "error": f"Could not download any of {len(url_errors)} URL(s). First: {url_errors[0]['error']}",
        }

    promo_item = _gallery_send_promo_item(db) if append_send_promo and db is not None else None

    try:
        await run_telegram_import_io(
            lambda storage: storage.save_batch_to_saved_only(items, caption=caption, promo_item=promo_item)
        )
    except ImageProcessFailedError as e:
        logger.warning("Telegram rejected saved-batch-urls err=%s", e)
        return {"error": f"Telegram rejected batch (corrupt or unsupported): {e}"}
    except Exception as e:
        logger.warning("saved-batch-urls Telegram err=%s", e, exc_info=True)
        return {"error": friendly_telegram_error(e)}

    out: dict = {
        "status": "saved_only",
        "message": "Saved to Telegram Saved Messages (grouped into albums of up to 10)",
        "count": len(items),
        "ok_urls": ok_urls,
    }
    if url_errors:
        out["errors"] = url_errors
    return out


@router.post("/url")
async def import_from_url(data: dict, db: Session = Depends(get_db)):
    """Single URL import, or batch Saved Messages when body includes urls[] + saved_only (same as /saved-batch-urls)."""
    try:
        urls_batch = data.get("urls")
        if isinstance(urls_batch, list) and len(urls_batch) > 0:
            if data.get("saved_only") is not True:
                return {"error": "urls array requires saved_only: true"}
            try:
                validated = SavedBatchUrlsBody(urls=urls_batch)
            except ValidationError as e:
                return {"error": f"Invalid urls: {e}"}
            return await _import_saved_batch_urls_impl(
                validated.urls,
                caption=_caption_from_body(data),
                append_send_promo=_truthy_flag(data.get("append_send_promo")),
                db=db,
            )

        url = data.get("url")
        pool_id = data.get("pool_id", 1)
        saved_only = data.get("saved_only") is True

        if not url:
            return {"error": "No URL provided"}
        if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
            return {"error": "Telegram API not configured"}

        logger.info("import/url: saved_only=%s url=%s", saved_only, url[:160])
        url_l = url.lower()
        is_large_media = any(
            url_l.split("?", 1)[0].endswith(ext) for ext in (".mp4", ".webm", ".mov", ".m4v", ".mkv")
        )
        timeout = 300.0 if is_large_media else 60.0
        try:
            file_bytes, content_type = await _httpx_get_media(url, timeout)
        except Exception as e:
            logger.warning("import/url fetch failed url=%s err=%s", url[:120], e)
            return {"error": _friendly_download_error(url, e)}

        file_bytes = await asyncio.to_thread(maybe_remux_mp4_for_playback, file_bytes)
        _reject_non_media_payload(file_bytes, url=url)
        media_type = _guess_media_type(url, content_type)
        cap = _caption_from_body(data)
        try:
            if saved_only:

                async def _saved(storage):
                    return await storage.save_to_saved_only(file_bytes, media_type, caption=cap)

                msg_id = await run_telegram_import_io(_saved)
                logger.info("saved_only: sent %s bytes (%s) to Saved Messages msg=%s", len(file_bytes), media_type, msg_id)
                out = {"status": "saved_only", "message": "Saved to Telegram Saved Messages"}
                if msg_id:
                    out["telegram_message_id"] = int(msg_id)
                return out

            record = await _import_bytes_to_pool(
                file_bytes,
                media_type,
                sanitize_import_source_url(url),
                pool_id,
                db,
            )
            if record:
                logger.info("Imported media id=%s pool_id=%s", record.id, pool_id)
                return {"status": "imported", "media_id": record.id}
            logger.warning("Import skipped (duplicate or unsupported format) url=%s", url[:80])
            return {"status": "skipped", "reason": "duplicate or unsupported format", "media_id": None}
        except ImageProcessFailedError as e:
            logger.warning("Telegram rejected import/url err=%s", e)
            return {"error": f"Telegram rejected this file (corrupt or unsupported): {e}"}
        except Exception as e:
            logger.warning("import/url Telegram err=%s", e, exc_info=True)
            return {"error": friendly_telegram_error(e)}
    except Exception as e:
        return _import_uncaught_error(e, endpoint="import/url")


@router.get("/watermark-config")
def import_watermark_config(db: Session = Depends(get_db)):
    """Extension/dashboard: promo watermark settings (no secrets)."""
    return watermark_config_public(db)


@router.post("/watermark-bytes")
async def import_watermark_bytes(
    file: UploadFile = File(...),
    media_type: str = Form("photo"),
    skip_watermark: str = Form("false"),
    watermark_config: str = Form(""),
    db: Session = Depends(get_db),
):
    """
    Apply promo text watermark to raw bytes (gallery ZIP/download/export).
    Returns unchanged body when disabled or skip_watermark=true.
    Optional watermark_config JSON overrides effective global settings.
    """
    raw = await file.read()
    if not raw:
        return Response(content=b"", status_code=400)
    skip = _truthy_flag(skip_watermark)
    cfg = None
    wc = (watermark_config or "").strip()
    if wc:
        try:
            import json

            payload = json.loads(wc)
            cfg = build_apply_config(db, override=payload)
        except Exception:
            cfg = None
    out = maybe_apply_media_watermark(raw, media_type, force_skip=skip, config=cfg)
    kind, ext = sniff_media_kind(out)
    mt = (media_type or "photo").lower()
    if kind == "video" or mt == "video":
        mime = "video/mp4"
        name = "media.mp4"
    elif ext == "png":
        mime = "image/png"
        name = "media.png"
    elif ext == "gif":
        mime = "image/gif"
        name = "media.gif"
    else:
        mime = "image/jpeg"
        name = "media.jpg"
    return Response(
        content=out,
        media_type=mime,
        headers={"Content-Disposition": f'inline; filename="{name}"'},
    )


# Soft cap for extension SW → R2 (avoids OOM); larger assets use CLI/organizer.
_R2_UPLOAD_MAX_BYTES = 80 * 1024 * 1024


@router.post("/watermark-upload-r2")
async def import_watermark_upload_r2(
    file: UploadFile = File(...),
    media_type: str = Form("photo"),
    destination: str = Form("library"),
    filename: str = Form(""),
    skip_watermark: str = Form("false"),
):
    """
    Watermark media bytes then upload to Cloudflare R2 (aof-media).

    destination: ``library`` → ``library/`` or ``sfw_x_promo`` → ``sfw-x-promo/``
    """
    from fastapi.responses import JSONResponse

    from app.services.r2_promo_upload import resolve_prefix, upload_bytes_to_r2

    raw = await file.read()
    if not raw:
        return JSONResponse({"ok": False, "error": "empty body"}, status_code=400)
    if len(raw) > _R2_UPLOAD_MAX_BYTES:
        return JSONResponse(
            {
                "ok": False,
                "error": f"file too large ({len(raw)} bytes); max {_R2_UPLOAD_MAX_BYTES} for SW R2 upload",
            },
            status_code=413,
        )

    dest_raw = (destination or "library").strip().lower()
    try:
        prefix = resolve_prefix(dest_raw)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    skip = _truthy_flag(skip_watermark)
    mt = (media_type or "photo").lower()
    if mt not in ("photo", "video"):
        mt = "photo"
    out = maybe_apply_media_watermark(raw, mt, force_skip=skip)
    watermarked = (not skip) and out != raw

    kind, ext = sniff_media_kind(out)
    if kind == "video" or mt == "video":
        mime = "video/mp4"
        default_name = "media.mp4"
        leaf_ext = "mp4"
    elif ext == "png":
        mime = "image/png"
        default_name = "media.png"
        leaf_ext = "png"
    elif ext == "gif":
        mime = "image/gif"
        default_name = "media.gif"
        leaf_ext = "gif"
    elif ext == "webp":
        mime = "image/webp"
        default_name = "media.webp"
        leaf_ext = "webp"
    else:
        mime = "image/jpeg"
        default_name = "media.jpg"
        leaf_ext = "jpg"

    leaf = (filename or "").strip() or (file.filename or "").strip() or default_name
    if "." not in leaf.rsplit("/", 1)[-1]:
        leaf = f"{leaf}.{leaf_ext}"
    leaf = leaf.rsplit("/", 1)[-1]

    try:
        from app.services.aof_lane_tag_map import build_aof_filename, is_aof_branded_filename
        import random

        if not is_aof_branded_filename(leaf):
            stem = leaf.rsplit(".", 1)[0] if "." in leaf else leaf
            leaf = build_aof_filename(
                name=stem or "media",
                index=random.randint(10000, 99999),
                ext=leaf_ext,
            )
    except Exception:
        pass

    try:
        result = upload_bytes_to_r2(
            out,
            filename=leaf,
            prefix=prefix,
            content_type=mime,
            timeout=180.0,
        )
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=503)
    except Exception as e:
        logger.exception("watermark-upload-r2 failed")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=502)

    return {
        "ok": True,
        "direct_url": result["direct_url"],
        "object_key": result["object_key"],
        "bucket": result.get("bucket"),
        "provider": result.get("provider", "r2"),
        "watermarked": watermarked,
        "destination": "sfw_x_promo" if prefix == "sfw-x-promo" else "library",
        "filename": leaf,
    }


@router.post("/zip-flywheel")
async def import_zip_flywheel(
    file: UploadFile = File(...),
    action: str = Form("host_gated"),
    host: str = Form("auto"),
    prefer_r2: str = Form("false"),
    filename: str = Form(""),
    label: str = Form(""),
    plan_id: str = Form(""),
    source_note: str = Form(""),
    db: Session = Depends(get_db),
):
    """
    Hybrid zip/media flywheel: R2 (small) or Pixeldrain (large) → gate wrap →
    optional loot modifier / Curated Pack shop bundle attach.

    actions: host_gated | loot_modifier | shop_bundle
    host: auto | r2 | pixeldrain
    downloads_promo is client-only (extension rename matrix).
    """
    from fastapi.responses import JSONResponse

    from app.services.pixeldrain_upload import PixeldrainUploadError
    from app.services.zip_flywheel import run_zip_flywheel

    raw = await file.read()
    if not raw:
        return JSONResponse({"ok": False, "error": "empty body"}, status_code=400)

    leaf = (filename or file.filename or "pack.zip").strip() or "pack.zip"
    act = (action or "host_gated").strip().lower()
    if act not in ("host_gated", "loot_modifier", "shop_bundle"):
        return JSONResponse({"ok": False, "error": "invalid_action"}, status_code=400)
    host_mode = (host or "auto").strip().lower()
    if host_mode not in ("auto", "r2", "pixeldrain"):
        return JSONResponse({"ok": False, "error": "invalid_host"}, status_code=400)
    prefer = (prefer_r2 or "").strip().lower() in ("1", "true", "yes", "on")
    pid: int | None = None
    if (plan_id or "").strip().isdigit():
        pid = int(plan_id.strip())

    try:
        result = run_zip_flywheel(
            db,
            raw,
            filename=leaf,
            action=act,  # type: ignore[arg-type]
            host=host_mode,  # type: ignore[arg-type]
            prefer_r2=prefer,
            label=(label or "").strip() or None,
            plan_id=pid,
            source_note=(source_note or "").strip() or "import_zip_flywheel",
        )
    except PixeldrainUploadError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=503)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except Exception as e:
        logger.exception("zip-flywheel failed")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=502)

    return result.as_dict()


@router.post("/process-bytes")
async def import_process_bytes(
    file: UploadFile = File(...),
    media_type: str = Form("photo"),
    crop_json: str = Form(""),
    watermark_json: str = Form(""),
    skip_watermark: str = Form("false"),
    db: Session = Depends(get_db),
):
    """
    Crop / blur bands + promo watermark on raw bytes (dashboard curate lightbox preview).
    Photos: crop + blur + watermark. Videos: watermark only (crop/blur ignored).
    """
    raw = await file.read()
    if not raw:
        return Response(content=b"", status_code=400)
    crop: ImageCropSettings | None = None
    wm: WatermarkOptions | None = None
    if crop_json.strip():
        try:
            crop = ImageCropSettings.model_validate(json.loads(crop_json))
        except Exception:
            return Response(content=b"invalid crop_json", status_code=400)
    if watermark_json.strip():
        try:
            wm = WatermarkOptions.model_validate(json.loads(watermark_json))
        except Exception:
            return Response(content=b"invalid watermark_json", status_code=400)
    if _truthy_flag(skip_watermark):
        wm = WatermarkOptions(skip=True) if wm is None else wm.model_copy(update={"skip": True})
    kind = (media_type or "photo").lower()
    if kind not in ("photo", "video"):
        kind = "photo"
    out = _process_media_bytes(raw, kind, db, crop=crop, wm=wm, context="default")
    kind_out, ext = sniff_media_kind(out)
    mt = kind
    if kind_out == "video" or mt == "video":
        mime = "video/mp4"
        name = "media.mp4"
    elif ext == "png":
        mime = "image/png"
        name = "media.png"
    elif ext == "gif":
        mime = "image/gif"
        name = "media.gif"
    else:
        mime = "image/jpeg"
        name = "media.jpg"
    return Response(
        content=out,
        media_type=mime,
        headers={"Content-Disposition": f'inline; filename="{name}"'},
    )


@router.post("/bytes")
async def import_from_bytes(
    file: UploadFile = File(...),
    pool_id: int = Form(1),
    saved_only: str = Form("false"),
    source: str = Form("extension:bytes"),
    caption: str = Form(""),
    sync: str = Form("false", description="Force synchronous Telegram upload (TBCC_FAST_IMPORT=0 behavior)"),
    skip_watermark: str = Form("false"),
    db: Session = Depends(get_db),
    x_tbcc_extension_job_id: str | None = Header(None, alias="X-TBCC-Extension-Job-Id"),
):
    """
    Import media from raw bytes (e.g. from extension after in-page fetch).
    Use this to bypass protected sites that block direct URL downloads
    (OnlyFans, FetLife, etc.): extension fetches in page context and POSTs here.
    """
    try:
        return await _import_from_bytes_impl(
            file=file,
            pool_id=pool_id,
            saved_only=saved_only,
            source=source,
            caption=caption,
            sync=sync,
            skip_watermark=skip_watermark,
            db=db,
            x_tbcc_extension_job_id=x_tbcc_extension_job_id,
        )
    except Exception as e:
        return _import_uncaught_error(e, endpoint="import/bytes")


async def _import_from_bytes_impl(
    *,
    file: UploadFile,
    pool_id: int,
    saved_only: str,
    source: str,
    caption: str,
    sync: str,
    skip_watermark: str,
    db: Session,
    x_tbcc_extension_job_id: str | None,
):
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        return {"error": "Telegram API not configured"}

    file_bytes = await file.read()
    saved_only_flag = str(saved_only or "").strip().lower() in ("true", "1", "yes", "on")
    logger.info(
        "import/bytes: saved_only=%s source=%s filename=%s size=%s",
        saved_only_flag,
        (source or "")[:80],
        (file.filename or "")[:120],
        len(file_bytes),
    )
    if not file_bytes:
        return {"error": "Empty file"}

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
    skip_wm = _truthy_flag(skip_watermark)

    force_sync = str(sync or "").strip().lower() in ("true", "1", "yes", "on")
    # Extension / dashboard: when pool imports are local-only, skip Celery fast-import and
    # handle the write inline in the API process (no Telegram I/O, no telegram queue usage).
    if not saved_only_flag:
        try:
            from app.services.local_media_storage import pool_import_local_enabled

            if pool_import_local_enabled():
                force_sync = True
        except Exception:
            # Fallback: respect explicit sync flag / TBCC_FAST_IMPORT
            logger.debug("import/bytes: pool_import_local_enabled check failed", exc_info=True)
    from app.services.import_pipeline import (
        create_staged_import_job,
        enqueue_import_job_processing,
        fast_import_enabled,
        update_job,
        job_to_public_dict,
    )

    if fast_import_enabled() and not force_sync:
        try:
            job = create_staged_import_job(
                db,
                file_bytes=file_bytes,
                pool_id=int(pool_id),
                saved_only=saved_only_flag,
                source=source or "extension:bytes",
                caption=cap,
                filename=file.filename,
                media_type=media_type,
                extension_job_id=x_tbcc_extension_job_id,
                skip_watermark=skip_wm,
            )
            task_id = enqueue_import_job_processing(job.id)
            if task_id:
                update_job(db, job, celery_task_id=task_id)
            try:
                from app.services.focus_profile import on_fast_import_queued

                focus_r = on_fast_import_queued(source or "import/bytes")
                if focus_r and focus_r.get("ok"):
                    logger.info("import/bytes: auto import_burst focus applied")
            except Exception:
                logger.debug("import/bytes: focus hook skipped", exc_info=True)
            body = job_to_public_dict(job)
            body["poll_url"] = f"/import/jobs/{job.id}"
            logger.info("import/bytes queued job_id=%s size=%s", job.id, job.byte_size)
            return body
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return _import_uncaught_error(e, endpoint="import/bytes fast-import")

    file_bytes = await asyncio.to_thread(maybe_remux_mp4_for_playback, file_bytes)

    try:
        with skip_watermark_context(skip_wm):
            if saved_only_flag:
                _reject_non_media_payload(file_bytes, url=source or "")

                async def _saved_only(storage):
                    msg_id = await storage.save_to_saved_only(file_bytes, media_type, caption=cap)
                    return ("saved_only", msg_id)

                result = await run_telegram_import_io(_saved_only)
            else:
                result = await _import_bytes_to_pool(
                    file_bytes,
                    media_type,
                    sanitize_import_source_url(source),
                    pool_id,
                    db,
                    skip_watermark=skip_wm,
                )
        if isinstance(result, tuple) and result[0] == "saved_only":
            msg_id = result[1] if len(result) > 1 else None
            logger.info(
                "saved_only (bytes): sent %s bytes (%s) to Saved Messages msg=%s",
                len(file_bytes),
                media_type,
                msg_id,
            )
            out = {"status": "saved_only", "message": "Saved to Telegram Saved Messages"}
            if msg_id:
                out["telegram_message_id"] = int(msg_id)
            return out
        if result == "saved_only":
            logger.info("saved_only (bytes): sent %s bytes (%s) to Saved Messages", len(file_bytes), media_type)
            return {"status": "saved_only", "message": "Saved to Telegram Saved Messages"}
        record = result
        if record:
            logger.info("Imported media id=%s pool_id=%s (bytes upload)", record.id, pool_id)
            return {"status": "imported", "media_id": record.id}
        return {"status": "skipped", "reason": "duplicate or unsupported format", "media_id": None}
    except ImageProcessFailedError as e:
        logger.warning("Telegram rejected bytes import err=%s", e)
        return {"error": f"Telegram rejected this file (corrupt or unsupported): {e}"}
    except Exception as e:
        logger.warning("import/bytes Telegram err=%s", e, exc_info=True)
        return {"error": friendly_telegram_error(e)}


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
    try:
        if body.saved_only:

            async def _saved(storage):
                await storage.save_to_saved_only(file_bytes, media_type, caption=None)

            await run_telegram_import_io(_saved)
            return {"status": "saved_only", "message": "Saved to Telegram Saved Messages"}

        record = await _import_bytes_to_pool(file_bytes, media_type, src, body.pool_id, db)
        if record:
            logger.info("Imported HLS media id=%s pool_id=%s", record.id, body.pool_id)
            return {"status": "imported", "media_id": record.id}
        return {"status": "skipped", "reason": "duplicate or unsupported format", "media_id": None}
    except ImageProcessFailedError as e:
        logger.warning("Telegram rejected HLS import err=%s", e)
        return {"error": f"Telegram rejected this file: {e}"}
    except Exception as e:
        logger.warning("import/hls-url Telegram err=%s", e, exc_info=True)
        return {"error": friendly_telegram_error(e)}


@router.post("/saved-batch")
async def import_saved_batch(
    files: Annotated[list[UploadFile], File(description="Repeat field name 'files' for each part")],
    caption: str = Form(""),
    append_send_promo: str = Form("false"),
    db: Session = Depends(get_db),
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

    promo_item = _gallery_send_promo_item(db) if _truthy_flag(append_send_promo) else None

    cap = (caption or "").strip() or None
    try:
        await run_telegram_import_io(
            lambda storage: storage.save_batch_to_saved_only(items, caption=cap, promo_item=promo_item)
        )
    except ImageProcessFailedError as e:
        logger.warning("Telegram rejected saved-batch err=%s", e)
        return {"error": f"Telegram rejected batch (corrupt or unsupported): {e}"}
    except Exception as e:
        logger.warning("saved-batch Telegram err=%s", e, exc_info=True)
        return {"error": friendly_telegram_error(e)}

    return {
        "status": "saved_only",
        "message": "Saved to Telegram Saved Messages (grouped into albums of up to 10)",
        "count": len(items),
    }


@router.post("/saved-from-bot-messages")
async def import_saved_from_bot_messages(body: SavedFromBotMessagesBody, db: Session = Depends(get_db)):
    """
    Fast Saved Messages path for Album Composer: Telethon copies media from the admin's DM
    with the bot (by message id) without Bot API download or byte re-upload.
    """
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        return {"error": "Telegram API not configured"}

    bot_peer = body.bot_username.strip().lstrip("@")
    if not bot_peer:
        return {"error": "bot_username required"}

    promo_item = _gallery_send_promo_item(db) if body.append_send_promo else None
    cap = (body.caption or "").strip() or None
    crop = body.crop
    wm = body.watermark
    use_crop = crop is not None and crop.applies()
    use_wm = _watermark_should_apply(db, wm, context="album_composer")
    use_bytes = use_crop or use_wm
    logger.info(
        "saved-from-bot-messages: %s media bot=@%s promo=%s crop=%s watermark=%s",
        body.media_count,
        bot_peer,
        bool(promo_item),
        use_crop,
        use_wm,
    )
    if use_bytes:
        file_items = [
            SavedFromBotFileItem(**f) if isinstance(f, dict) else f for f in (body.files or [])
        ]
        try:
            processed = await _download_album_bot_processed_bytes(
                bot_peer=bot_peer,
                media_count=body.media_count,
                message_ids=body.message_ids or None,
                anchor_max_message_id=body.anchor_max_message_id,
                files=file_items or None,
                db=db,
                crop=crop,
                wm=wm,
            )
        except ImageProcessFailedError as e:
            return {"error": f"Telegram rejected batch: {e}"}
        except Exception as e:
            return {"error": f"Could not download from album bot: {_exc_detail(e)}"}

        async def _save_processed(storage):
            await storage.save_batch_to_saved_only(processed, caption=cap, promo_item=promo_item)
            return len(processed)

        try:
            count = await run_telegram_album_composer_io(_save_processed)
        except ImageProcessFailedError as e:
            return {"error": f"Telegram rejected batch: {e}"}
        except Exception as e:
            return {"error": friendly_telegram_error(e)}
        return {
            "status": "saved_only",
            "message": "Saved to Telegram Saved Messages (watermark/crop applied)",
            "count": count,
        }
    try:
        await run_telegram_album_composer_io(
            lambda storage: storage.save_bot_messages_to_saved_only(
                bot_peer,
                body.media_count,
                caption=cap,
                message_ids=body.message_ids or None,
                anchor_max_message_id=body.anchor_max_message_id,
                promo_item=promo_item,
            )
        )
    except ValueError as e:
        if body.files:
            logger.info("saved-from-bot-messages instant copy failed (%s); using file_id fallback", e)
            return await _saved_batch_from_bot_files(
                body.files,
                cap,
                body.append_send_promo,
                db,
                use_album_session=True,
            )
        return {"error": str(e)}
    except ImageProcessFailedError as e:
        logger.warning("Telegram rejected saved-from-bot-messages err=%s", e)
        return {"error": f"Telegram rejected batch (corrupt or unsupported): {e}"}
    except Exception as e:
        logger.warning("saved-from-bot-messages Telegram err=%s", e, exc_info=True)
        return {"error": friendly_telegram_error(e)}

    return {
        "status": "saved_only",
        "message": "Saved to Telegram Saved Messages (instant server-side copy)",
        "count": body.media_count,
    }


@router.post("/saved-batch-urls")
async def import_saved_batch_urls(body: SavedBatchUrlsBody, db: Session = Depends(get_db)):
    """Alias for batch Saved Messages (albums). Prefer POST /import/url with urls[] if this route is missing (older servers)."""
    cap = body.caption.strip() if body.caption else None
    return await _import_saved_batch_urls_impl(
        body.urls,
        caption=cap,
        append_send_promo=body.append_send_promo,
        db=db,
    )


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
    wm_raw = data.get("watermark")
    wm = WatermarkOptions.model_validate(wm_raw) if isinstance(wm_raw, dict) else None
    if data.get("apply_watermark") is True and wm is None:
        wm = WatermarkOptions(enabled=True)
    use_wm = _watermark_should_apply(db, wm, context="saved_import")

    try:

        async def _index(storage):
            if use_wm:
                return await storage.index_from_saved_messages_watermarked(
                    pool_id, source, db, limit=limit, wm=wm
                )
            return await storage.index_from_saved_messages(pool_id, source, db, limit=limit)

        result = await run_telegram_import_io(_index)
    except Exception as e:
        logger.exception("import/from-saved failed: %s", e)
        return {"error": friendly_telegram_error(e)}
    return {"status": "ok", **result}


def _parse_channel_import_request(data: dict) -> dict | tuple[str, ...]:
    """Return error string or parsed kwargs dict for channel import."""
    channel = (data.get("channel") or data.get("identifier") or "").strip()
    if not channel:
        return ("channel is required (@channel, t.me link, or -100… id)",)
    try:
        pool_id = int(data.get("pool_id") or 1)
    except (TypeError, ValueError):
        return ("Invalid pool_id",)
    try:
        limit = int(data.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    limit = min(max(limit, 1), 200)
    media_types = str(data.get("media_types") or "both").strip().lower() or "both"
    if media_types not in ("both", "photos", "videos"):
        return ("media_types must be both, photos, or videos",)
    message_thread_id = data.get("message_thread_id")
    if message_thread_id is not None and message_thread_id != "":
        try:
            message_thread_id = int(message_thread_id)
        except (TypeError, ValueError):
            return ("Invalid message_thread_id (forum topic id)",)
    else:
        message_thread_id = None
    source = (data.get("source") or f"telegram:{channel}").strip() or f"telegram:{channel}"
    if message_thread_id is not None:
        source = f"{source}#topic:{message_thread_id}"
    topic_title = str(data.get("topic_title") or "").strip() or None
    sync = _truthy_flag(data.get("sync"))
    apply_watermark = _truthy_flag(data.get("apply_watermark"))
    return {
        "channel": channel,
        "pool_id": pool_id,
        "limit": limit,  # max NEW items to store (deduped)
        "media_types": media_types,
        "message_thread_id": message_thread_id,
        "source_label": source,
        "topic_title": topic_title,
        "sync": sync,
        "apply_watermark": apply_watermark,
    }


def _queue_channel_import(db: Session, parsed: dict) -> dict:
    from app.services.import_pipeline import (
        create_channel_import_job,
        enqueue_channel_import_job,
        job_to_public_dict,
        update_job,
    )

    job = create_channel_import_job(
        db,
        channel=parsed["channel"],
        pool_id=parsed["pool_id"],
        limit=parsed["limit"],
        media_types=parsed["media_types"],
        message_thread_id=parsed["message_thread_id"],
        source_label=parsed["source_label"],
        topic_title=parsed.get("topic_title"),
        apply_watermark=bool(parsed.get("apply_watermark")),
    )
    task_id = enqueue_channel_import_job(job.id)
    if task_id:
        update_job(db, job, celery_task_id=task_id)
    body = job_to_public_dict(job)
    body["poll_url"] = f"/import/jobs/{job.id}"
    body["async"] = True
    logger.info(
        "channel import queued job_id=%s channel=%s topic=%s limit=%s pool=%s",
        job.id,
        parsed["channel"][:80],
        parsed["message_thread_id"],
        parsed["limit"],
        parsed["pool_id"],
    )
    return body


@router.post("/from-channel")
async def import_from_telegram_channel(data: dict, db: Session = Depends(get_db)):
    """
    Import recent media from a Telegram channel/group into a pool (admin Telethon session).
    Forwards or downloads each item into Saved Messages, then indexes as pending media.
    The admin account must be a member (or admin) of the target chat.
    Body: pool_id, channel (@name, t.me/…, or -100… id), limit (1–200 new items, deduped),
    media_types (both|photos|videos).
    Runs in background on the Celery telegram queue unless sync=true (small tests only).
    """
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        return {"error": "Telegram API not configured"}
    parsed = _parse_channel_import_request(data)
    if isinstance(parsed, tuple):
        return {"error": parsed[0]}

    if not parsed["sync"]:
        return _queue_channel_import(db, parsed)

    try:

        async def _import(storage):
            return await storage.import_from_telegram_channel(
                parsed["channel"],
                parsed["pool_id"],
                parsed["source_label"],
                db,
                limit=parsed["limit"],
                media_types=parsed["media_types"],
                message_thread_id=parsed["message_thread_id"],
                apply_watermark=bool(parsed.get("apply_watermark")),
            )

        result = await run_telegram_import_io(_import)
    except Exception as e:
        logger.exception("import/from-channel failed: %s", e)
        return {"error": friendly_telegram_error(e)}
    return {"status": "ok", **result}


@router.get("/forum-topics")
async def import_list_forum_topics(channel: str = Query(..., min_length=1)):
    """
    List forum topics for a channel/group by @username, t.me link, or -100… id.
    Topic `id` is the message_thread_id used when importing from a specific subtopic.
    """
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        return {"topics": [], "error": "Telegram API not configured"}
    ident = channel.strip()
    if not ident:
        return {"topics": [], "error": "channel query param required"}

    try:

        async def _list(storage):
            return await storage.list_forum_topics(ident)

        topics = await run_telegram_io(_list)
    except Exception as e:
        logger.exception("import/forum-topics failed: %s", e)
        return {"topics": [], "error": friendly_telegram_error(e)}
    return {"topics": topics, "error": None}


@router.post("/from-channel-batch")
async def import_from_telegram_channel_batch(data: dict, db: Session = Depends(get_db)):
    """
    Import several forum topics from one group into different pools.
    Body: channel, limit (default per row), media_types (default), imports: [
      { message_thread_id, pool_id, limit?, media_types? }, ...
    ]
    Each topic is queued as its own background job unless sync=true.
    """
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        return {"error": "Telegram API not configured"}
    channel = (data.get("channel") or data.get("identifier") or "").strip()
    if not channel:
        return {"error": "channel is required"}
    raw = data.get("imports")
    if not isinstance(raw, list) or not raw:
        return {"error": "imports must be a non-empty list"}
    sync = _truthy_flag(data.get("sync"))
    default_limit = 50
    try:
        default_limit = int(data.get("limit") or 50)
    except (TypeError, ValueError):
        pass
    default_limit = min(max(default_limit, 1), 200)
    default_media = str(data.get("media_types") or "both").strip().lower() or "both"
    if default_media not in ("both", "photos", "videos"):
        return {"error": "media_types must be both, photos, or videos"}
    apply_watermark = _truthy_flag(data.get("apply_watermark"))

    if not sync:
        jobs: list[dict] = []
        for row in raw[:30]:
            if not isinstance(row, dict):
                continue
            try:
                pool_id = int(row.get("pool_id"))
                topic_id = int(row.get("message_thread_id"))
            except (TypeError, ValueError):
                jobs.append({"error": "Each import needs pool_id and message_thread_id"})
                continue
            try:
                lim = int(row.get("limit") or default_limit)
            except (TypeError, ValueError):
                lim = default_limit
            lim = min(max(lim, 1), 200)
            mt = str(row.get("media_types") or default_media).strip().lower() or default_media
            if mt not in ("both", "photos", "videos"):
                mt = default_media
            source = f"telegram:{channel}#topic:{topic_id}"
            title = str(row.get("topic_title") or "").strip()
            parsed = {
                "channel": channel,
                "pool_id": pool_id,
                "limit": lim,
                "media_types": mt,
                "message_thread_id": topic_id,
                "source_label": source,
                "topic_title": title or None,
                "apply_watermark": apply_watermark,
            }
            body = _queue_channel_import(db, parsed)
            body["message_thread_id"] = topic_id
            body["topic_title"] = title or None
            jobs.append(body)
        return {"status": "queued", "async": True, "jobs": jobs}

    results: list[dict] = []
    try:
        for row in raw[:30]:
            if not isinstance(row, dict):
                continue
            try:
                pool_id = int(row.get("pool_id"))
                topic_id = int(row.get("message_thread_id"))
            except (TypeError, ValueError):
                results.append({"error": "Each import needs pool_id and message_thread_id"})
                continue
            try:
                lim = int(row.get("limit") or default_limit)
            except (TypeError, ValueError):
                lim = default_limit
            lim = min(max(lim, 1), 200)
            mt = str(row.get("media_types") or default_media).strip().lower() or default_media
            if mt not in ("both", "photos", "videos"):
                mt = default_media
            source = f"telegram:{channel}#topic:{topic_id}"
            title = str(row.get("topic_title") or "").strip()

            async def _import(storage, *, _pid=pool_id, _tid=topic_id, _lim=lim, _mt=mt, _src=source):
                return await storage.import_from_telegram_channel(
                    channel,
                    _pid,
                    _src,
                    db,
                    limit=_lim,
                    media_types=_mt,
                    message_thread_id=_tid,
                    apply_watermark=apply_watermark,
                )

            part = await run_telegram_import_io(_import)
            results.append(
                {
                    "message_thread_id": topic_id,
                    "pool_id": pool_id,
                    "topic_title": title or None,
                    **part,
                }
            )
    except Exception as e:
        logger.exception("import/from-channel-batch failed: %s", e)
        return {"error": friendly_telegram_error(e), "results": results}
    return {"status": "ok", "results": results}


@router.get("/storage-hub-lanes")
def list_storage_hub_import_lanes(db: Session = Depends(get_db)) -> dict:
    """Storage & Bot Hangar subtopics mapped to active AOF channel pools (Media Library import UI)."""
    from app.services.aof_growth_hub import list_storage_hub_import_lanes as _lanes

    return _lanes(db)


@router.post("/from-storage-hub")
def import_from_storage_hub(data: dict, db: Session = Depends(get_db)) -> dict:
    """
    Import NEW media from Storage Hub forum subtopics into matching AOF channel pools.
    Skips duplicates already in each pool; scans backward until batch size is met.
    Body: limit (new items per lane, 1–200), network_keys (optional list), media_types.
    """
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        return {"error": "Telegram API not configured"}
    from app.services.aof_growth_hub import queue_storage_hub_deposits, storage_pool_seed_batch_size

    raw_keys = data.get("network_keys")
    topic_keys: list[str] | None = None
    if raw_keys is not None:
        if not isinstance(raw_keys, list):
            return {"error": "network_keys must be a list of lane keys (milf, abg, …)"}
        topic_keys = [str(k).strip().lower() for k in raw_keys if str(k).strip()]
        if not topic_keys:
            return {"error": "Select at least one storage lane"}

    try:
        limit = int(data.get("limit") or storage_pool_seed_batch_size())
    except (TypeError, ValueError):
        limit = storage_pool_seed_batch_size()
    limit = min(max(limit, 1), 200)

    media_types = str(data.get("media_types") or "both").strip().lower() or "both"
    if media_types not in ("both", "photos", "videos"):
        return {"error": "media_types must be both, photos, or videos"}

    apply_watermark = _truthy_flag(data.get("apply_watermark"))

    report = queue_storage_hub_deposits(
        db,
        limit=limit,
        topic_keys=topic_keys,
        media_types=media_types,
        content_lanes_only=topic_keys is None,
        include_topic_mirror=False,
        apply_watermark=apply_watermark,
    )
    jobs = []
    for row in report.get("jobs") or []:
        job_id = row.get("job_id")
        if not job_id:
            continue
        jobs.append({**row, "poll_url": f"/import/jobs/{job_id}"})
    return {
        "ok": True,
        "async": True,
        "limit_per_lane": report.get("limit_per_topic"),
        "matched_count": report.get("matched_count"),
        "jobs": jobs,
    }
