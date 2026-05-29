import asyncio
import logging
import os

from telethon import TelegramClient
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto, MessageMediaWebPage

from app.database.session import SessionLocal
from app.models.source import Source
from app.services.scrape_run_service import ERROR_CATALOG, normalize_media_types, utcnow
from app.services.telegram_storage import TelegramStorage
from app.utils.telegram_peer import normalize_telegram_username, resolve_telethon_entity

logger = logging.getLogger(__name__)


def normalize_telegram_identifier(raw: str) -> str:
    """Accept @name, name, or https://t.me/name/... for display / storage metadata."""
    return normalize_telegram_username(raw)


def _message_media_kind(message) -> str | None:
    media = message.media
    if not media:
        return None
    if isinstance(media, MessageMediaWebPage):
        wp = media.webpage
        if wp is None or (not getattr(wp, "photo", None) and not getattr(wp, "document", None)):
            return None
        if getattr(wp, "document", None):
            mime = (getattr(wp.document, "mime_type", None) or "").lower()
            if "video" in mime:
                return "video"
            return "photo"
        return "photo"
    if isinstance(media, MessageMediaPhoto):
        return "photo"
    if isinstance(media, MessageMediaDocument):
        mime = (media.document.mime_type or "").lower()
        if "video" in mime:
            return "video"
        if "image" in mime or mime in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            return "photo"
        return "document"
    return "document"


def _accepts_kind(kind: str | None, media_types: str) -> bool:
    if not kind:
        return False
    mt = normalize_media_types(media_types)
    if mt == "both":
        return kind in ("photo", "video")
    if mt == "photos":
        return kind == "photo"
    if mt == "videos":
        return kind == "video"
    return False


def _empty_stats() -> dict:
    return {
        "messages_scanned": 0,
        "stored": 0,
        "skipped_duplicate": 0,
        "skipped_media_type": 0,
        "skipped_no_media": 0,
        "errors_count": 0,
        "errors": [],
        "fatal": False,
        "error_summary": None,
    }


def _merge_stats(into: dict, part: dict) -> None:
    for k in (
        "messages_scanned",
        "stored",
        "skipped_duplicate",
        "skipped_media_type",
        "skipped_no_media",
        "errors_count",
    ):
        into[k] = int(into.get(k) or 0) + int(part.get(k) or 0)
    into["errors"] = list(into.get("errors") or []) + list(part.get("errors") or [])
    if part.get("fatal"):
        into["fatal"] = True
    if part.get("error_summary") and not into.get("error_summary"):
        into["error_summary"] = part["error_summary"]


async def _scrape_one_source(source: Source, client, storage: TelegramStorage, db) -> dict:
    stats = _empty_stats()
    ident = normalize_telegram_identifier(source.identifier)
    if not ident:
        stats["errors"].append(
            {
                "code": "empty_identifier",
                "message": "Source has empty channel identifier.",
                "fix": "Edit the source and set a @channel or t.me link.",
            }
        )
        stats["errors_count"] = 1
        stats["fatal"] = True
        return stats

    media_types = normalize_media_types(getattr(source, "media_types", None))
    limit = int(getattr(source, "max_messages_per_run", None) or 50)
    limit = max(1, min(limit, 500))

    try:
        entity = await resolve_telethon_entity(client, source.identifier)
        etitle = getattr(entity, "title", None) or getattr(entity, "username", None) or str(
            getattr(entity, "id", "?")
        )
        logger.info("Resolved entity: %s", etitle)
    except Exception as e:
        logger.exception("Cannot resolve %r: %s", ident, e)
        cat = ERROR_CATALOG["resolve_entity_failed"]
        stats["errors"].append(
            {
                "code": "resolve_entity_failed",
                "message": cat["message"],
                "fix": cat["fix"],
                "detail": str(e)[:400],
            }
        )
        stats["errors_count"] = 1
        stats["fatal"] = True
        return stats

    scanned_with_media = 0
    try:
        async for message in client.iter_messages(entity, limit=limit):
            kind = _message_media_kind(message)
            if not kind:
                stats["skipped_no_media"] += 1
                continue
            if not _accepts_kind(kind, media_types):
                stats["skipped_media_type"] += 1
                continue
            scanned_with_media += 1
            stats["messages_scanned"] = scanned_with_media
            if storage.is_duplicate_message(message, source.pool_id or 0, db):
                stats["skipped_duplicate"] += 1
                await asyncio.sleep(0.05)
                continue
            try:
                rec = await storage.store_from_message(
                    message,
                    source=source.identifier or ident,
                    pool_id=source.pool_id or 0,
                    db=db,
                )
                if rec is not None:
                    stats["stored"] += 1
                else:
                    stats["skipped_duplicate"] += 1
            except Exception as inner:
                stats["errors_count"] += 1
                stats["errors"].append(
                    {
                        "code": "store_failed",
                        "message": f"Failed to store message id={message.id}",
                        "fix": "Check scraper.session login and Saved Messages access.",
                        "detail": str(inner)[:300],
                    }
                )
                logger.warning("store_from_message failed for msg id=%s: %s", message.id, inner)
            await asyncio.sleep(0.5)
        logger.info(
            "Scrape done source id=%s: scanned=%s stored=%s dup=%s type_skip=%s pool_id=%s",
            source.id,
            stats["messages_scanned"],
            stats["stored"],
            stats["skipped_duplicate"],
            stats["skipped_media_type"],
            source.pool_id,
        )
    except Exception as e:
        logger.exception("Scrape failed for source id=%s (%s): %s", source.id, ident, e)
        cat = ERROR_CATALOG.get("scraper_session", {})
        stats["errors"].append(
            {
                "code": "scrape_iter_failed",
                "message": cat.get("message") or "Scrape iteration failed.",
                "fix": cat.get("fix") or "Check Celery logs and scraper.session.",
                "detail": str(e)[:400],
            }
        )
        stats["errors_count"] += 1
        stats["fatal"] = True
    return stats


async def run_scraper(
    api_id: str,
    api_hash: str,
    session_name: str = "scraper",
    source_id: int | None = None,
) -> dict:
    """
    Pull media from Telegram channel(s) into a content pool.
    Returns aggregate stats dict (see _empty_stats).
    """
    total = _empty_stats()
    client = TelegramClient(session_name, int(api_id), api_hash)
    storage = TelegramStorage(client)

    try:
        await client.start()
    except Exception as e:
        cat = ERROR_CATALOG["scraper_session"]
        total["errors"].append(
            {
                "code": "scraper_session",
                "message": cat["message"],
                "fix": cat["fix"],
                "detail": str(e)[:400],
            }
        )
        total["errors_count"] = 1
        total["fatal"] = True
        return total

    db = SessionLocal()
    try:
        q = db.query(Source).filter(Source.active == True, Source.source_type == "telegram_channel")
        if source_id is not None:
            q = q.filter(Source.id == source_id)
        sources = q.all()
        if not sources:
            total["error_summary"] = "No matching active Telegram source."
            total["errors"].append(
                {
                    "code": "no_source",
                    "message": "No matching active Telegram channel source.",
                    "fix": "Enable Active on the source or check source_id.",
                }
            )
            total["errors_count"] = 1
            return total
        for source in sources:
            part = await _scrape_one_source(source, client, storage, db)
            _merge_stats(total, part)
            if source_id is not None:
                source.last_scraped_at = utcnow()
                db.commit()
    finally:
        db.close()
        await client.disconnect()
    return total


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _sid = os.environ.get("SOURCE_ID", "").strip()
    _optional_id = int(_sid) if _sid.isdigit() else None
    stats = asyncio.run(
        run_scraper(
            api_id=os.environ["API_ID"],
            api_hash=os.environ["API_HASH"],
            source_id=_optional_id,
        )
    )
    print(stats)
