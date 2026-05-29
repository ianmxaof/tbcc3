"""List installed custom emoji packs and emojis on the poster Telethon account."""

from __future__ import annotations

import logging
from typing import Any

from telethon import TelegramClient
from telethon.tl.functions.messages import GetEmojiStickersRequest, GetStickerSetRequest
from telethon.tl.types import DocumentAttributeCustomEmoji, InputStickerSetID

from app.services.telegram_custom_emoji import build_tg_emoji_tag

logger = logging.getLogger(__name__)


def _placeholder_from_alt(alt: str | None) -> str:
    raw = (alt or "").strip()
    if not raw:
        return "⭐"
    # Telegram alt may be multiple emoji; custom emoji tag needs exactly one char.
    for ch in raw:
        if ch.strip():
            return ch
    return raw[0] if raw else "⭐"


async def list_installed_custom_emoji_packs(client: TelegramClient) -> list[dict[str, Any]]:
    """Non-archived custom emoji sticker sets on this account."""
    out: list[dict[str, Any]] = []
    try:
        result = await client(GetEmojiStickersRequest(hash=0))
    except Exception as e:
        logger.warning("GetEmojiStickers failed: %s", e)
        return out

    sets = getattr(result, "sets", None) or []
    for s in sets:
        ss = getattr(s, "set", s)
        if ss is None:
            continue
        out.append(
            {
                "id": int(getattr(ss, "id", 0) or 0),
                "access_hash": int(getattr(ss, "access_hash", 0) or 0),
                "short_name": str(getattr(ss, "short_name", "") or ""),
                "title": str(getattr(ss, "title", "") or ""),
                "count": int(getattr(ss, "count", 0) or 0),
            }
        )
    out.sort(key=lambda x: (x.get("title") or x.get("short_name") or "").lower())
    return out


async def fetch_custom_emoji_pack(
    client: TelegramClient,
    *,
    short_name: str | None = None,
    set_id: int | None = None,
    access_hash: int | None = None,
) -> dict[str, Any]:
    """Full pack: documents + ready-to-paste tg-emoji tags."""
    if short_name:
        from telethon.tl.types import InputStickerSetShortName

        inp = InputStickerSetShortName(short_name=short_name.strip())
    elif set_id is not None and access_hash is not None:
        inp = InputStickerSetID(id=int(set_id), access_hash=int(access_hash))
    else:
        raise ValueError("short_name or set_id+access_hash required")

    full = await client(GetStickerSetRequest(stickerset=inp, hash=0))
    ss = full.set
    emojis: list[dict[str, Any]] = []
    for doc in full.documents or []:
        doc_id = int(getattr(doc, "id", 0) or 0)
        alt = ""
        free = True
        for attr in getattr(doc, "attributes", None) or []:
            if isinstance(attr, DocumentAttributeCustomEmoji):
                alt = str(getattr(attr, "alt", "") or "")
                free = bool(getattr(attr, "free", False))
                break
        ph = _placeholder_from_alt(alt)
        tag = build_tg_emoji_tag(doc_id, ph)
        emojis.append(
            {
                "document_id": doc_id,
                "alt": alt,
                "placeholder": ph,
                "tag": tag,
                "free": free,
            }
        )

    return {
        "id": int(ss.id),
        "short_name": str(ss.short_name or ""),
        "title": str(ss.title or ""),
        "count": len(emojis),
        "emojis": emojis,
    }
