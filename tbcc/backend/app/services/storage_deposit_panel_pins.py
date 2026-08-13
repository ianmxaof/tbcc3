"""Pinned /deposit control panel in every Storage Hub forum lane (payment bot)."""

from __future__ import annotations

import logging
import os
from typing import Any

from app.data.aof_storage_hub_map import (
    AOF_STORAGE_TOPIC_MAP,
    INBOX_CHANNEL_IDENT,
    INBOX_CHANNEL_TITLE,
    INBOX_TOPIC_ID,
    INBOX_TOPIC_TITLE,
)
from app.services.hub_lane_control import format_lane_hub_panel_html, lane_hub_control_keyboard
from app.services.storage_topic_deposit import storage_hub_chat_id_int

logger = logging.getLogger(__name__)

REDIS_PREFIX = "tbcc:storage:deposit:panel:msg"


def storage_deposit_panels_enabled() -> bool:
    return (os.getenv("TBCC_STORAGE_DEPOSIT_PANEL_PINNED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def panel_redis_key(chat_id: int, message_thread_id: int | None) -> str:
    tid = int(message_thread_id or 0)
    return f"{REDIS_PREFIX}:{int(chat_id)}:{tid}"


def get_stored_panel_message_id(chat_id: int, message_thread_id: int | None) -> int | None:
    try:
        raw = _redis().get(panel_redis_key(chat_id, message_thread_id))
        if raw is not None:
            mid = int(raw)
            return mid if mid > 0 else None
    except Exception:
        logger.debug("deposit panel msg read failed", exc_info=True)
    return None


def set_stored_panel_message_id(chat_id: int, message_thread_id: int | None, message_id: int) -> None:
    try:
        _redis().set(panel_redis_key(chat_id, message_thread_id), str(int(message_id)))
    except Exception:
        logger.debug("deposit panel msg write failed", exc_info=True)


def storage_deposit_panel_targets() -> list[dict[str, Any]]:
    """All forum lanes + inbox topic + inbox shortcut channel."""
    out: list[dict[str, Any]] = []
    seen_threads: set[int] = set()
    for row in AOF_STORAGE_TOPIC_MAP:
        if not row.network_key:
            continue
        tid = int(row.message_thread_id)
        if tid in seen_threads:
            continue
        seen_threads.add(tid)
        out.append(
            {
                "chat_id": storage_hub_chat_id_int(),
                "message_thread_id": tid,
                "topic_title": row.topic_title,
                "network_key": row.network_key,
            }
        )
    out.append(
        {
            "chat_id": storage_hub_chat_id_int(),
            "message_thread_id": int(INBOX_TOPIC_ID),
            "topic_title": INBOX_TOPIC_TITLE,
            "network_key": "inbox",
        }
    )
    out.append(
        {
            "chat_id": int(INBOX_CHANNEL_IDENT),
            "message_thread_id": None,
            "topic_title": INBOX_CHANNEL_TITLE,
            "network_key": "inbox",
        }
    )
    return out


async def ensure_storage_deposit_panel(
    bot,
    *,
    chat_id: int,
    message_thread_id: int | None,
    topic_title: str,
    force_new: bool = False,
) -> dict[str, Any]:
    """Post or refresh the lane control panel for one Storage Hub topic (singleton at bottom)."""
    from telegram.constants import ParseMode

    from app.services.hub_panel_message import ensure_singleton_panel_message

    target_network_key = None
    for row in AOF_STORAGE_TOPIC_MAP:
        if message_thread_id and int(row.message_thread_id) == int(message_thread_id):
            target_network_key = row.network_key
            break
    if message_thread_id and int(message_thread_id) == int(INBOX_TOPIC_ID):
        target_network_key = "inbox"

    text = format_lane_hub_panel_html(
        thread_title=topic_title,
        network_key=target_network_key,
    )
    markup = lane_hub_control_keyboard(target_network_key)

    return await ensure_singleton_panel_message(
        bot,
        chat_id=int(chat_id),
        message_thread_id=message_thread_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
        force_new=force_new,
        get_stored_message_id=lambda: get_stored_panel_message_id(chat_id, message_thread_id),
        set_stored_message_id=lambda mid: set_stored_panel_message_id(chat_id, message_thread_id, mid),
        panel_label="lane_deposit",
    )


async def refresh_storage_deposit_panel_http(
    *,
    chat_id: int,
    message_thread_id: int | None,
    topic_title: str,
    network_key: str | None,
) -> dict[str, Any]:
    """Refresh a lane panel via Bot API (for Celery / composer workers without a live bot app)."""
    import httpx

    token = (os.getenv("TBCC_ALBUM_COMPOSER_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
    stored_mid = get_stored_panel_message_id(chat_id, message_thread_id)
    if not token or not stored_mid:
        return {"ok": False, "skipped": True, "reason": "no_token_or_panel"}

    text = format_lane_hub_panel_html(thread_title=topic_title, network_key=network_key)
    markup = lane_hub_control_keyboard(network_key)
    kb = markup.to_dict() if hasattr(markup, "to_dict") else markup

    payload: dict[str, Any] = {
        "chat_id": int(chat_id),
        "message_id": int(stored_mid),
        "text": text[:4000],
        "parse_mode": "HTML",
        "reply_markup": kb,
        "disable_web_page_preview": True,
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.post(f"https://api.telegram.org/bot{token}/editMessageText", json=payload)
        body = r.json()
        if body.get("ok"):
            return {"ok": True, "action": "edited", "message_id": int(stored_mid)}
        return {"ok": False, "telegram": body}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def ensure_all_storage_deposit_panels(bot, *, force_new: bool = False) -> dict[str, Any]:
    """Bootstrap pinned deposit panels across every mapped Storage Hub lane."""
    import asyncio

    if not storage_deposit_panels_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}
    results: list[dict[str, Any]] = []
    errors = 0
    pause_s = float(os.getenv("TBCC_STORAGE_HUB_PANEL_BOOTSTRAP_PAUSE_S") or "1.2")
    for i, target in enumerate(storage_deposit_panel_targets()):
        if i > 0 and pause_s > 0:
            await asyncio.sleep(pause_s)
        try:
            out = await ensure_storage_deposit_panel(
                bot,
                chat_id=int(target["chat_id"]),
                message_thread_id=target.get("message_thread_id"),
                topic_title=str(target.get("topic_title") or ""),
                force_new=force_new,
            )
            results.append({**target, **out})
        except Exception as e:
            errors += 1
            logger.warning(
                "deposit panel bootstrap failed lane=%s: %s",
                target.get("topic_title"),
                e,
                exc_info=True,
            )
            results.append({**target, "ok": False, "error": str(e)[:200]})
    posted = sum(1 for r in results if r.get("action") == "posted")
    edited = sum(1 for r in results if r.get("action") == "edited")
    return {
        "ok": errors == 0,
        "posted": posted,
        "edited": edited,
        "errors": errors,
        "lanes": len(results),
        "results": results,
    }
