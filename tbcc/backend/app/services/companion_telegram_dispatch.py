"""Deliver companion generation results back to Telegram."""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)


def _bot_token() -> str:
    return (
        os.getenv("TBCC_COMPANION_BOT_TOKEN")
        or os.getenv("COMPANION_BOT_TOKEN")
        or os.getenv("TBCC_LLM_CHAT_BOT_TOKEN")
        or ""
    ).strip()


async def send_result_photo_bytes(
    *,
    chat_id: int,
    image_bytes: bytes,
    caption: str = "",
    filename: str = "result.jpg",
    parse_mode: str | None = None,
) -> bool:
    token = _bot_token()
    if not token or not image_bytes:
        return False
    api = f"https://api.telegram.org/bot{token}"
    files = {"photo": (filename, image_bytes, "image/jpeg")}
    form: dict[str, str] = {"chat_id": str(chat_id)}
    if caption:
        form["caption"] = caption[:1024]
    if parse_mode:
        form["parse_mode"] = parse_mode
    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.post(f"{api}/sendPhoto", data=form, files=files)
        if r.is_success:
            return True
        logger.warning("sendPhoto bytes failed %s: %s", r.status_code, (r.text or "")[:300])
    return False


async def send_result_photo(*, chat_id: int, image_url: str, caption: str = "") -> bool:
    token = _bot_token()
    if not token:
        logger.error("companion dispatch: no bot token configured")
        return False
    api = f"https://api.telegram.org/bot{token}"
    payload: dict[str, object] = {"chat_id": chat_id, "photo": image_url}
    if caption:
        payload["caption"] = caption[:1024]
    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.post(f"{api}/sendPhoto", json=payload)
        if r.is_success:
            return True
        logger.warning("sendPhoto url failed %s: %s", r.status_code, (r.text or "")[:300])
    # fallback: download bytes then multipart
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            img = await client.get(image_url)
            img.raise_for_status()
            data = img.content
            files = {"photo": ("result.jpg", data, "image/jpeg")}
            form = {"chat_id": str(chat_id)}
            if caption:
                form["caption"] = caption[:1024]
            r2 = await client.post(f"{api}/sendPhoto", data=form, files=files)
            if r2.is_success:
                return True
            logger.warning("sendPhoto bytes failed %s: %s", r2.status_code, (r2.text or "")[:300])
    except Exception as e:
        logger.warning("companion dispatch download failed: %s", e)
    return False


async def send_result_message(
    *,
    chat_id: int,
    text: str,
    parse_mode: str | None = "HTML",
    reply_markup: dict | None = None,
) -> bool:
    token = _bot_token()
    if not token:
        return False
    api = f"https://api.telegram.org/bot{token}"
    payload: dict[str, object] = {"chat_id": chat_id, "text": text[:4096]}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{api}/sendMessage", json=payload)
        return r.is_success
