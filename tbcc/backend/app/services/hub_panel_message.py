"""Singleton Storage Hub panel messages — one live panel per topic, bottom of thread."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

logger = logging.getLogger(__name__)


def hub_panel_pin_messages() -> bool:
    """When false (default), panels stay at the bottom as the newest message."""
    return (os.getenv("TBCC_STORAGE_HUB_PANEL_PIN") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


async def delete_panel_message(
    bot,
    *,
    chat_id: int,
    message_id: int,
    message_thread_id: int | None = None,
) -> None:
    if int(message_id) <= 0:
        return
    if hub_panel_pin_messages():
        from app.utils.telegram_forum import bot_api_forum_thread_api_kwargs

        try:
            pin_kw: dict[str, Any] = {"chat_id": int(chat_id), "message_id": int(message_id)}
            forum_api = bot_api_forum_thread_api_kwargs(message_thread_id)
            if forum_api:
                await bot.unpin_chat_message(**pin_kw, api_kwargs=forum_api)
            else:
                await bot.unpin_chat_message(**pin_kw)
        except Exception:
            logger.debug("hub panel unpin failed chat=%s msg=%s", chat_id, message_id, exc_info=True)
    try:
        await bot.delete_message(chat_id=int(chat_id), message_id=int(message_id))
    except Exception:
        logger.debug("hub panel delete failed chat=%s msg=%s", chat_id, message_id, exc_info=True)


async def ensure_singleton_panel_message(
    bot,
    *,
    chat_id: int,
    message_thread_id: int | None,
    text: str,
    parse_mode: Any,
    reply_markup: Any,
    force_new: bool,
    get_stored_message_id: Callable[[], int | None],
    set_stored_message_id: Callable[[int], None],
    panel_label: str = "panel",
) -> dict[str, Any]:
    """
    Edit the stored panel when possible; otherwise delete the stale copy and post fresh
    at the bottom so only one instance exists per topic.
    """
    stored_mid = get_stored_message_id()
    send_kw: dict[str, Any] = {
        "chat_id": int(chat_id),
        "text": text,
        "parse_mode": parse_mode,
        "reply_markup": reply_markup,
        "disable_web_page_preview": True,
    }
    from app.utils.telegram_forum import bot_api_forum_thread_id, bot_api_forum_thread_api_kwargs

    api_thread = bot_api_forum_thread_id(message_thread_id)
    if api_thread:
        send_kw["message_thread_id"] = api_thread

    if stored_mid and force_new:
        await delete_panel_message(
            bot,
            chat_id=int(chat_id),
            message_id=int(stored_mid),
            message_thread_id=message_thread_id,
        )
        set_stored_message_id(0)
        stored_mid = None

    if stored_mid and not force_new:
        try:
            await bot.edit_message_text(message_id=int(stored_mid), **send_kw)
            return {
                "ok": True,
                "action": "edited",
                "message_id": int(stored_mid),
                "panel": panel_label,
            }
        except Exception:
            logger.debug(
                "hub panel edit failed panel=%s chat=%s thread=%s msg=%s",
                panel_label,
                chat_id,
                message_thread_id,
                stored_mid,
                exc_info=True,
            )
            await delete_panel_message(
                bot,
                chat_id=int(chat_id),
                message_id=int(stored_mid),
                message_thread_id=message_thread_id,
            )
            set_stored_message_id(0)

    msg = await bot.send_message(**send_kw)
    mid = int(msg.message_id)
    set_stored_message_id(mid)

    if hub_panel_pin_messages():
        try:
            pin_kw: dict[str, Any] = {
                "chat_id": int(chat_id),
                "message_id": mid,
                "disable_notification": True,
            }
            forum_api = bot_api_forum_thread_api_kwargs(message_thread_id)
            if forum_api:
                await bot.pin_chat_message(**pin_kw, api_kwargs=forum_api)
            else:
                await bot.pin_chat_message(**pin_kw)
        except Exception:
            logger.debug(
                "hub panel pin failed panel=%s chat=%s thread=%s",
                panel_label,
                chat_id,
                message_thread_id,
                exc_info=True,
            )

    return {
        "ok": True,
        "action": "posted",
        "message_id": mid,
        "panel": panel_label,
    }
