"""Pinned live Q&A intake counter — always at top of APPROVE/DENY topic."""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_storage_hub_map import GATEKEEPER_REVIEW_TOPIC_TITLE
from app.services.gatekeeper_review import (
    count_quarantine_waiting,
    inbox_quarantine_buffer_count,
    review_chat_id,
)
from app.services.quarantine_batch_review import lane_quarantine_buffer_count

logger = logging.getLogger(__name__)

REDIS_COUNTER_PREFIX = "tbcc:qa:live_counter:msg"


def qa_live_counter_enabled() -> bool:
    return (os.getenv("TBCC_QA_LIVE_COUNTER_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def counter_redis_key(chat_id: int) -> str:
    return f"{REDIS_COUNTER_PREFIX}:{int(chat_id)}"


def get_stored_counter_message_id(chat_id: int) -> int | None:
    try:
        raw = _redis().get(counter_redis_key(chat_id))
        if raw is not None:
            mid = int(raw)
            return mid if mid > 0 else None
    except Exception:
        logger.debug("qa live counter msg read failed", exc_info=True)
    return None


def set_stored_counter_message_id(chat_id: int, message_id: int) -> None:
    try:
        _redis().set(counter_redis_key(chat_id), str(int(message_id)))
    except Exception:
        logger.debug("qa live counter msg write failed", exc_info=True)


def format_qa_live_counter_html(db: Session) -> str:
    waiting = count_quarantine_waiting(db)
    inbox_buf = inbox_quarantine_buffer_count()
    lane_bufs: list[str] = []
    try:
        from app.data.aof_storage_hub_map import CONTENT_LANE_NETWORK_KEYS

        for lk in sorted(CONTENT_LANE_NETWORK_KEYS):
            if lk in ("inbox", "packs"):
                continue
            n = lane_quarantine_buffer_count(lk)
            if n > 0:
                lane_bufs.append(f"{lk}:{n}")
    except Exception:
        pass

    title = GATEKEEPER_REVIEW_TOPIC_TITLE or "Q&A INTAKE"
    status = "🟢 clear" if waiting < 1 and inbox_buf < 1 and not lane_bufs else "🟡 action"
    lines = [
        f"📊 <b>{title}</b> · {status}",
        f"⏳ <b>Waiting quarantine:</b> {waiting}",
    ]
    if inbox_buf > 0:
        lines.append(f"📥 Inbox buffer (not posted): <b>{inbox_buf}</b>")
    if lane_bufs:
        lines.append(f"📦 Lane buffers: <code>{', '.join(lane_bufs[:12])}</code>")
    lines.append(
        "<i>Decided items auto-clear from this topic · "
        "<code>/review</code> bulk · <code>/qapanel</code> master</i>"
    )
    return "\n".join(lines)


async def ensure_qa_live_counter(bot, *, force_new: bool = False) -> dict[str, Any]:
    """Pin or refresh the live waiting counter at the top of the Q&A topic."""
    from telegram.constants import ParseMode

    from app.database.session import SessionLocal
    from app.data.aof_storage_hub_map import GATEKEEPER_REVIEW_TOPIC_ID
    from app.utils.telegram_forum import bot_api_forum_thread_api_kwargs, bot_api_forum_thread_id

    if not qa_live_counter_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    chat_id = int(review_chat_id())
    thread_id = int(GATEKEEPER_REVIEW_TOPIC_ID or 1)
    with SessionLocal() as db:
        text = format_qa_live_counter_html(db)

    stored_mid = get_stored_counter_message_id(chat_id)
    send_kw: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": ParseMode.HTML,
        "disable_web_page_preview": True,
    }
    api_thread = bot_api_forum_thread_id(thread_id)
    if api_thread:
        send_kw["message_thread_id"] = api_thread

    if stored_mid and not force_new:
        try:
            await bot.edit_message_text(message_id=int(stored_mid), **send_kw)
            return {"ok": True, "action": "edited", "message_id": int(stored_mid)}
        except Exception:
            logger.debug("qa live counter edit failed msg=%s", stored_mid, exc_info=True)
            try:
                await bot.delete_message(chat_id=chat_id, message_id=int(stored_mid))
            except Exception:
                pass
            set_stored_counter_message_id(chat_id, 0)

    msg = await bot.send_message(**send_kw)
    mid = int(msg.message_id)
    set_stored_counter_message_id(chat_id, mid)
    try:
        pin_kw: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": mid,
            "disable_notification": True,
        }
        forum_api = bot_api_forum_thread_api_kwargs(thread_id)
        if forum_api:
            await bot.pin_chat_message(**pin_kw, api_kwargs=forum_api)
        else:
            await bot.pin_chat_message(**pin_kw)
    except Exception:
        logger.debug("qa live counter pin failed chat=%s msg=%s", chat_id, mid, exc_info=True)
    return {"ok": True, "action": "posted", "message_id": mid}


def refresh_qa_live_counter_http() -> dict[str, Any]:
    """Refresh counter via Bot API (Celery / post-decide hook without PTB bot)."""
    import httpx

    from app.database.session import SessionLocal
    from app.data.aof_storage_hub_map import GATEKEEPER_REVIEW_TOPIC_ID
    from app.services.gatekeeper_review import _bot_token
    from app.utils.telegram_forum import bot_api_forum_thread_id

    if not qa_live_counter_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}
    token = _bot_token()
    if not token:
        return {"ok": False, "reason": "bot_token_unset"}

    chat_id = int(review_chat_id())
    thread_id = int(GATEKEEPER_REVIEW_TOPIC_ID or 1)
    with SessionLocal() as db:
        text = format_qa_live_counter_html(db)

    stored_mid = get_stored_counter_message_id(chat_id)
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    api_thread = bot_api_forum_thread_id(thread_id)
    if api_thread:
        payload["message_thread_id"] = api_thread

    base = f"https://api.telegram.org/bot{token}"
    with httpx.Client(timeout=20) as client:
        if stored_mid:
            edit_payload = dict(payload)
            edit_payload["message_id"] = int(stored_mid)
            r = client.post(f"{base}/editMessageText", json=edit_payload)
            data = r.json() if r.content else {}
            if r.status_code == 200 and data.get("ok"):
                return {"ok": True, "action": "edited", "message_id": int(stored_mid)}
            try:
                client.post(
                    f"{base}/deleteMessage",
                    json={"chat_id": chat_id, "message_id": int(stored_mid)},
                )
            except Exception:
                pass

        r = client.post(f"{base}/sendMessage", json=payload)
        data = r.json() if r.content else {}
        if r.status_code != 200 or not data.get("ok"):
            return {"ok": False, "error": str(data)[:300]}
        mid = int((data.get("result") or {}).get("message_id") or 0)
        set_stored_counter_message_id(chat_id, mid)
        pin_payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": mid,
            "disable_notification": True,
        }
        if api_thread:
            pin_payload["message_thread_id"] = api_thread
        try:
            client.post(f"{base}/pinChatMessage", json=pin_payload)
        except Exception:
            pass
        return {"ok": True, "action": "posted", "message_id": mid}
