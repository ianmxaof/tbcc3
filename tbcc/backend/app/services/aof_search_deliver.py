"""Deliver AOF search results as DM albums via the loot bot."""

from __future__ import annotations

import html
import io
import logging
from typing import Any

from sqlalchemy.orm import Session
from telegram import Bot, InputMediaPhoto, InputMediaVideo
from telegram.error import TelegramError

from app.models.media import Media
from app.services.loot_preview_delivery import _batch_load_media_bytes, _media_send_bucket
from app.services.telegram_content_protection import bot_protect_content_kw

logger = logging.getLogger(__name__)


def build_search_result_caption(result: dict[str, Any], *, query: str) -> str:
    parsed = result.get("parsed") or {}
    lane_keys = parsed.get("lane_keys") or []
    emoji = result.get("primary_emoji") or "🔍"
    lanes = ", ".join(html.escape(k.replace("_", " ")) for k in lane_keys[:3])
    count = len(result.get("items") or [])
    lines = [
        f"<b>{emoji} AOF Search</b>",
        f"<i>{html.escape((query or parsed.get('raw') or '').strip()[:120])}</i>",
    ]
    if lanes:
        lines.append(f"Lanes: {lanes}")
    lines.append(f"{count} item(s) · surface <code>{html.escape(str(result.get('surface') or ''))}</code>")
    link = (result.get("library_link") or "").strip()
    if link:
        lines.append(f'<a href="{html.escape(link, quote=True)}">Archive of Filth →</a>')
    return "\n".join(lines)[:1024]


async def send_aof_search_album(
    db: Session,
    *,
    bot: Bot,
    chat_id: int,
    media_rows: list[Media],
    caption_html: str,
    spoiler_default: bool = True,
) -> dict[str, Any]:
    delivery: dict[str, Any] = {"albums_sent": 0, "media_sent": 0, "notes": []}
    if not media_rows:
        delivery["notes"].append("no_media_rows")
        return delivery

    payloads, notes = await _batch_load_media_bytes(media_rows, db=db)
    delivery["notes"].extend(notes)
    if not payloads:
        delivery["notes"].append("no_deliverable_bytes")
        return delivery

    protect_kw = bot_protect_content_kw()
    chunk_size = 10
    first_cap = True
    for start in range(0, len(payloads), chunk_size):
        chunk = payloads[start : start + chunk_size]
        media_group: list = []
        for idx, (row, data, fname) in enumerate(chunk):
            bio = io.BytesIO(data)
            bio.name = fname
            cap = caption_html if first_cap and idx == 0 and start == 0 else None
            bucket = _media_send_bucket(data, row)
            if bucket == "video":
                media_group.append(
                    InputMediaVideo(
                        media=bio,
                        caption=cap,
                        parse_mode="HTML" if cap else None,
                        has_spoiler=spoiler_default,
                        **protect_kw,
                    )
                )
            else:
                media_group.append(
                    InputMediaPhoto(
                        media=bio,
                        caption=cap,
                        parse_mode="HTML" if cap else None,
                        has_spoiler=spoiler_default,
                        **protect_kw,
                    )
                )
        try:
            await bot.send_media_group(
                chat_id=int(chat_id),
                media=media_group,
                read_timeout=180,
                write_timeout=180,
                connect_timeout=30,
            )
            delivery["albums_sent"] = int(delivery.get("albums_sent") or 0) + 1
            delivery["media_sent"] = int(delivery.get("media_sent") or 0) + len(chunk)
            first_cap = False
        except TelegramError as e:
            logger.warning("aof search album send failed chat=%s: %s", chat_id, e)
            delivery["notes"].append(f"send_failed:{e}")
            break
    return delivery
