"""Pinned control panels — SENT VAULT + inbox intake (Storage Hub)."""

from __future__ import annotations

import logging
import os
from typing import Any

from app.data.aof_storage_hub_map import INBOX_CHANNEL_IDENT, INBOX_CHANNEL_TITLE, INBOX_TOPIC_ID, INBOX_TOPIC_TITLE
from app.services.storage_sent_cache import storage_sent_cache_topic_id
from app.services.storage_topic_deposit import storage_hub_chat_id_int

logger = logging.getLogger(__name__)

REDIS_PREFIX = "tbcc:storage:hub:panel:msg"


def hub_control_panels_enabled() -> bool:
    return (os.getenv("TBCC_STORAGE_HUB_CONTROL_PANELS") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def panel_redis_key(panel_kind: str, chat_id: int, message_thread_id: int | None) -> str:
    tid = int(message_thread_id or 0)
    return f"{REDIS_PREFIX}:{panel_kind}:{int(chat_id)}:{tid}"


def get_stored_hub_panel_message_id(panel_kind: str, chat_id: int, message_thread_id: int | None) -> int | None:
    try:
        raw = _redis().get(panel_redis_key(panel_kind, chat_id, message_thread_id))
        if raw is not None:
            mid = int(raw)
            return mid if mid > 0 else None
    except Exception:
        logger.debug("hub panel msg read failed kind=%s", panel_kind, exc_info=True)
    return None


def set_stored_hub_panel_message_id(
    panel_kind: str,
    chat_id: int,
    message_thread_id: int | None,
    message_id: int,
) -> None:
    try:
        _redis().set(panel_redis_key(panel_kind, chat_id, message_thread_id), str(int(message_id)))
    except Exception:
        logger.debug("hub panel msg write failed kind=%s", panel_kind, exc_info=True)


async def ensure_sent_cache_panel(bot, *, force_new: bool = False) -> dict[str, Any]:
    from telegram.constants import ParseMode

    from app.services.hub_panel_message import ensure_singleton_panel_message
    from app.services.sent_cache_control import format_sent_cache_panel_html, sent_cache_control_keyboard

    chat_id = storage_hub_chat_id_int()
    thread_id = storage_sent_cache_topic_id()
    text = format_sent_cache_panel_html()
    markup = sent_cache_control_keyboard()

    return await ensure_singleton_panel_message(
        bot,
        chat_id=chat_id,
        message_thread_id=thread_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
        force_new=force_new,
        get_stored_message_id=lambda: get_stored_hub_panel_message_id("sent_cache", chat_id, thread_id),
        set_stored_message_id=lambda mid: set_stored_hub_panel_message_id("sent_cache", chat_id, thread_id, mid),
        panel_label="sent_cache",
    )


async def ensure_inbox_intake_panel(bot, *, force_new: bool = False) -> dict[str, Any]:
    from telegram.constants import ParseMode

    from app.services.hub_panel_message import ensure_singleton_panel_message
    from app.services.intake_scheduler import format_status_text
    from bots.intake_control_handlers import intake_control_keyboard

    chat_id = storage_hub_chat_id_int()
    thread_id = int(INBOX_TOPIC_ID)
    text = (
        f"<b>📥 Inbox intake panel</b>\n\n"
        f"{format_status_text()}\n\n"
        "<i>Batch deposits, album flush, and global intake cadence.</i>"
    )
    markup = intake_control_keyboard()

    return await ensure_singleton_panel_message(
        bot,
        chat_id=chat_id,
        message_thread_id=thread_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
        force_new=force_new,
        get_stored_message_id=lambda: get_stored_hub_panel_message_id("inbox", chat_id, thread_id),
        set_stored_message_id=lambda mid: set_stored_hub_panel_message_id("inbox", chat_id, thread_id, mid),
        panel_label="inbox",
    )


async def _ensure_qa_master_panel(bot, *, force_new: bool = False) -> dict[str, Any]:
    from app.services.qa_master_panel import ensure_qa_master_panel

    return await ensure_qa_master_panel(bot, force_new=force_new)


async def ensure_all_hub_control_panels(bot, *, force_new: bool = False) -> dict[str, Any]:
    """Bootstrap lane panels (via deposit pins) + SENT VAULT + inbox intake."""
    if not hub_control_panels_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    from app.services.storage_deposit_panel_pins import ensure_all_storage_deposit_panels

    lane_report = await ensure_all_storage_deposit_panels(bot, force_new=force_new)
    extra: list[dict[str, Any]] = []
    for coro_name, coro in (
        ("sent_cache", ensure_sent_cache_panel(bot, force_new=force_new)),
        ("inbox", ensure_inbox_intake_panel(bot, force_new=force_new)),
        ("qa_master", _ensure_qa_master_panel(bot, force_new=force_new)),
    ):
        try:
            extra.append(await coro)
        except Exception as e:
            logger.warning("hub panel bootstrap failed panel=%s: %s", coro_name, e, exc_info=True)
            extra.append({"ok": False, "panel": coro_name, "error": str(e)[:200]})

    return {
        "ok": bool(lane_report.get("ok")) and all(r.get("ok") for r in extra),
        "lanes": lane_report,
        "special_panels": extra,
    }
