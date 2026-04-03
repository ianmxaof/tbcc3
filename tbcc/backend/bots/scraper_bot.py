import asyncio
import logging
import os

from telethon import TelegramClient
from telethon.tl.types import MessageMediaWebPage

from app.database.session import SessionLocal
from app.models.source import Source
from app.services.telegram_storage import TelegramStorage

logger = logging.getLogger(__name__)


def normalize_telegram_identifier(raw: str) -> str:
    """Accept @name, name, or https://t.me/name/... for Telethon iter_messages."""
    s = (raw or "").strip()
    if not s:
        return s
    if "t.me/" in s:
        try:
            part = s.split("t.me/", 1)[1].split("/")[0].split("?")[0]
            s = part
        except IndexError:
            pass
    if s.startswith("@"):
        s = s[1:]
    return s


async def run_scraper(
    api_id: str,
    api_hash: str,
    session_name: str = "scraper",
    source_id: int | None = None,
):
    """
    Pull media from Telegram channel(s) into a content pool.

    If source_id is set, only that source row is scraped (must be active, telegram_channel).
    Otherwise all active telegram_channel sources are scraped.
    """
    client = TelegramClient(session_name, int(api_id), api_hash)
    storage = TelegramStorage(client)

    await client.start()

    db = SessionLocal()
    try:
        q = db.query(Source).filter(Source.active == True, Source.source_type == "telegram_channel")
        if source_id is not None:
            q = q.filter(Source.id == source_id)
        sources = q.all()
        if not sources:
            logger.warning(
                "Telegram scrape: no matching source (source_id=%s). Check Sources tab: active, type telegram_channel.",
                source_id,
            )
            return
        for source in sources:
            ident = normalize_telegram_identifier(source.identifier)
            if not ident:
                logger.warning("Source id=%s has empty identifier, skipping", source.id)
                continue
            logger.info("Scraping source id=%s identifier=%s pool_id=%s", source.id, ident, source.pool_id)
            try:
                entity = await client.get_entity(ident)
                etitle = getattr(entity, "title", None) or getattr(entity, "username", None) or str(
                    getattr(entity, "id", "?")
                )
                logger.info("Resolved entity: %s", etitle)
            except Exception as e:
                logger.exception(
                    "Cannot resolve %r — wrong username, private channel without access, or typo: %s",
                    ident,
                    e,
                )
                continue
            seen = 0
            stored = 0
            try:
                async for message in client.iter_messages(ident, limit=50):
                    if not message.media:
                        continue
                    if isinstance(message.media, MessageMediaWebPage):
                        wp = message.media.webpage
                        if wp is None or (
                            not getattr(wp, "photo", None) and not getattr(wp, "document", None)
                        ):
                            continue
                    seen += 1
                    try:
                        rec = await storage.store_from_message(
                            message,
                            source=source.identifier or ident,
                            pool_id=source.pool_id or 0,
                            db=db,
                        )
                        if rec is not None:
                            stored += 1
                    except Exception as inner:
                        logger.warning("store_from_message failed for msg id=%s: %s", message.id, inner)
                    await asyncio.sleep(0.5)
                logger.info(
                    "Scrape done source id=%s: messages_with_media=%s new_media_rows=%s (check Media tab, status=pending, pool_id=%s)",
                    source.id,
                    seen,
                    stored,
                    source.pool_id,
                )
            except Exception as e:
                logger.exception("Scrape failed for source id=%s (%s): %s", source.id, ident, e)
    finally:
        db.close()
        await client.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _sid = os.environ.get("SOURCE_ID", "").strip()
    _optional_id = int(_sid) if _sid.isdigit() else None
    asyncio.run(
        run_scraper(
            api_id=os.environ["API_ID"],
            api_hash=os.environ["API_HASH"],
            source_id=_optional_id,
        )
    )
