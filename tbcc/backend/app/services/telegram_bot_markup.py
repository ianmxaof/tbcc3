"""Attach inline keyboards via payment Bot API (reliable on channel posts)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _bot_token() -> str:
    return (os.getenv("BOT_TOKEN") or os.getenv("TBCC_PAYMENT_BOT_TOKEN") or "").strip()


def buttons_to_inline_keyboard(buttons_data: list) -> dict[str, Any] | None:
    """[{text, url}, ...] → Bot API reply_markup.inline_keyboard."""
    rows: list[list[dict[str, str]]] = []
    for row in buttons_data or []:
        items = row if isinstance(row, list) else [row]
        out_row: list[dict[str, str]] = []
        for btn in items:
            if not isinstance(btn, dict):
                continue
            text = str(btn.get("text") or "").strip()
            url = str(btn.get("url") or "").strip()
            if text and url.startswith(("http://", "https://", "tg://")):
                out_row.append({"text": text[:64], "url": url[:512]})
        if out_row:
            rows.append(out_row)
    return {"inline_keyboard": rows} if rows else None


async def attach_inline_keyboard(
    chat_id: str | int,
    message_id: int,
    buttons_data: list,
    *,
    timeout: float = 30.0,
) -> bool:
    """
    editMessageReplyMarkup — payment bot must be admin in the channel.
    Used when Telethon send_file drops URL buttons on re-uploaded pool media.
    """
    token = _bot_token()
    markup = buttons_to_inline_keyboard(buttons_data)
    if not token or not markup or not message_id:
        return False
    try:
        cid: str | int = chat_id
        if isinstance(chat_id, str) and chat_id.strip().lstrip("-").isdigit():
            cid = int(chat_id.strip())
    except (TypeError, ValueError):
        cid = chat_id
    url = f"https://api.telegram.org/bot{token}/editMessageReplyMarkup"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                url,
                json={
                    "chat_id": cid,
                    "message_id": int(message_id),
                    "reply_markup": markup,
                },
            )
            data = r.json()
    except Exception as e:
        logger.warning("editMessageReplyMarkup failed chat=%s msg=%s: %s", chat_id, message_id, e)
        return False
    if not data.get("ok"):
        desc = (data.get("description") or str(data))[:200]
        logger.warning(
            "editMessageReplyMarkup rejected chat=%s msg=%s: %s "
            "(payment bot must be admin in this chat with post/edit rights)",
            chat_id,
            message_id,
            desc,
        )
        return False
    return True


async def send_message_with_inline_keyboard(
    chat_id: str | int,
    *,
    text: str,
    buttons_data: list,
    reply_to_message_id: int | None = None,
    message_thread_id: int | None = None,
    parse_mode: str = "HTML",
    disable_notification: bool = False,
    timeout: float = 30.0,
) -> int | None:
    """sendMessage with inline keyboard — payment bot must be admin in channel."""
    token = _bot_token()
    markup = buttons_to_inline_keyboard(buttons_data)
    if not token or not markup or not (text or "").strip():
        return None
    try:
        cid: str | int = chat_id
        if isinstance(chat_id, str) and chat_id.strip().lstrip("-").isdigit():
            cid = int(chat_id.strip())
    except (TypeError, ValueError):
        cid = chat_id
    body: dict[str, Any] = {
        "chat_id": cid,
        "text": text[:4096],
        "parse_mode": parse_mode,
        "reply_markup": markup,
        "disable_notification": disable_notification,
    }
    if reply_to_message_id:
        body["reply_to_message_id"] = int(reply_to_message_id)
    if message_thread_id:
        body["message_thread_id"] = int(message_thread_id)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json=body)
            data = r.json()
    except Exception as e:
        logger.warning("sendMessage+keyboard failed chat=%s: %s", chat_id, e)
        return None
    if not data.get("ok"):
        logger.warning(
            "sendMessage+keyboard rejected chat=%s: %s",
            chat_id,
            (data.get("description") or data)[:200],
        )
        return None
    result = data.get("result") or {}
    return int(result.get("message_id") or 0) or None


async def send_photo_with_inline_keyboard(
    chat_id: str | int,
    *,
    photo_path: str | Path,
    caption: str = "",
    buttons_data: list,
    parse_mode: str = "HTML",
    disable_notification: bool = False,
    timeout: float = 60.0,
) -> int | None:
    """sendPhoto with inline URL keyboard — payment bot must be admin in channel."""
    token = _bot_token()
    markup = buttons_to_inline_keyboard(buttons_data)
    path = Path(photo_path)
    if not token or not markup or not path.is_file():
        return None
    try:
        cid: str | int = chat_id
        if isinstance(chat_id, str) and chat_id.strip().lstrip("-").isdigit():
            cid = int(chat_id.strip())
    except (TypeError, ValueError):
        cid = chat_id
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    data = {
        "chat_id": cid,
        "caption": (caption or "")[:1024],
        "parse_mode": parse_mode,
        "reply_markup": json.dumps(markup),
        "disable_notification": disable_notification,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            with path.open("rb") as f:
                r = await client.post(
                    url,
                    data=data,
                    files={"photo": (path.name, f, "image/png")},
                )
            payload = r.json()
    except Exception as e:
        logger.warning("sendPhoto+keyboard failed chat=%s: %s", chat_id, e)
        return None
    if not payload.get("ok"):
        logger.warning(
            "sendPhoto+keyboard rejected chat=%s: %s",
            chat_id,
            (payload.get("description") or payload)[:200],
        )
        return None
    result = payload.get("result") or {}
    return int(result.get("message_id") or 0) or None
