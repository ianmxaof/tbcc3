"""Move deposited Storage Hub media into SENT CACHE with ✅ + category emoji stamps."""

from __future__ import annotations

import asyncio
import logging
import os

from sqlalchemy.orm import Session

from app.data.aof_storage_hub_map import (
    STORAGE_HUB_IDENT,
    category_emoji_for_network_key,
)
from app.models.media import Media

logger = logging.getLogger(__name__)

SENT_CACHE_STAMP = "✅"


def storage_sent_cache_enabled() -> bool:
    return (os.getenv("TBCC_STORAGE_SENT_CACHE_ENABLED") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def storage_sent_cache_topic_id() -> int:
    raw = (os.getenv("TBCC_STORAGE_SENT_CACHE_TOPIC_ID") or "12345").strip()
    return int(raw)


def sent_cache_caption(network_key: str | None) -> str:
    return f"{SENT_CACHE_STAMP}{category_emoji_for_network_key(network_key)}"


def _coerce_message(messages):
    if messages is None:
        return None
    if isinstance(messages, list):
        return messages[0] if messages else None
    return messages


async def move_deposit_batch_to_sent_cache(
    storage,
    db: Session,
    *,
    stored_messages: list[dict],
    network_key: str | None,
    hub_ident: str = STORAGE_HUB_IDENT,
) -> dict[str, int]:
    """
    Copy indexed items into SENT CACHE (caption ✅+category emoji), delete from source topic,
    and repoint pool Media rows to the new in-chat message ids.
    """
    if not storage_sent_cache_enabled():
        return {"skipped": 1, "moved": 0, "errors": 0}
    if not stored_messages:
        return {"moved": 0, "errors": 0}

    from app.utils.telegram_peer import resolve_telethon_entity

    cache_tid = storage_sent_cache_topic_id()
    caption = sent_cache_caption(network_key)
    client = storage.client
    entity = await resolve_telethon_entity(client, hub_ident)

    moved = 0
    errors = 0
    moved_items: list[dict[str, int]] = []
    for row in stored_messages:
        if not isinstance(row, dict):
            continue
        try:
            old_mid = int(row.get("message_id") or 0)
            media_id = int(row.get("media_id") or 0)
        except (TypeError, ValueError):
            errors += 1
            continue
        if old_mid <= 0 or media_id <= 0:
            errors += 1
            continue
        try:
            messages = await client.get_messages(entity, ids=old_mid)
            msg = _coerce_message(messages)
            if not msg or not getattr(msg, "media", None):
                errors += 1
                continue
            sent = await client.send_file(
                entity,
                msg,
                caption=caption,
                reply_to=cache_tid,
                silent=True,
            )
            new_mid = int(getattr(sent, "id", 0) or 0)
            if new_mid <= 0:
                errors += 1
                continue
            await client.delete_messages(entity, [old_mid])
            rec = db.query(Media).filter(Media.id == media_id).first()
            if rec:
                rec.telegram_message_id = new_mid
                db.commit()
            moved += 1
            moved_items.append({"media_id": media_id, "cache_message_id": new_mid})
            await asyncio.sleep(0.12)
        except Exception:
            logger.warning(
                "sent cache move failed media_id=%s msg_id=%s",
                media_id,
                old_mid,
                exc_info=True,
            )
            errors += 1
    return {
        "moved": moved,
        "errors": errors,
        "cache_topic_id": cache_tid,
        "caption": caption,
        "moved_items": moved_items,
    }
