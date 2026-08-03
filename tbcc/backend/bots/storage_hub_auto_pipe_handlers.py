"""Payment bot — auto-pipe lane media into Q&A quarantine review."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.data.aof_storage_hub_map import GATEKEEPER_REVIEW_TOPIC_ID, SENT_CACHE_TOPIC
from app.services.storage_auto_pipe import signal_lane_auto_pipe, storage_auto_pipe_enabled
from app.services.storage_topic_deposit import resolve_storage_topic_row, storage_hub_chat_id_int

logger = logging.getLogger(__name__)


def _message_has_media(msg) -> bool:
    return bool(
        msg
        and (
            getattr(msg, "photo", None)
            or getattr(msg, "video", None)
            or getattr(msg, "document", None)
            or getattr(msg, "animation", None)
        )
    )


def _is_bot_noise(msg) -> bool:
    text = (getattr(msg, "text", None) or getattr(msg, "caption", None) or "").strip()
    if text.startswith("/"):
        return True
    if getattr(msg, "via_bot", None):
        return True
    return False


async def on_storage_hub_lane_media_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Channel post in a mapped Storage lane → debounced auto-pipe to Q&A review."""
    if not storage_auto_pipe_enabled():
        return
    msg = update.effective_message
    chat = update.effective_chat
    if not msg or not chat:
        return
    if int(chat.id) != storage_hub_chat_id_int():
        return
    thread_id = getattr(msg, "message_thread_id", None)
    if not thread_id:
        return
    tid = int(thread_id)
    if tid == int(GATEKEEPER_REVIEW_TOPIC_ID or 0) or tid == int(SENT_CACHE_TOPIC.message_thread_id):
        return
    if getattr(msg, "sender_chat", None) and getattr(msg.sender_chat, "id", None) == int(chat.id):
        # Channel self-post noise — still may be media forwards
        pass
    if _is_bot_noise(msg) and not _message_has_media(msg):
        return
    if not _message_has_media(msg):
        return
    row = resolve_storage_topic_row(tid)
    if not row or not row.network_key or row.network_key in ("inbox", "packs"):
        return
    try:
        signal_lane_auto_pipe(row.network_key, tid)
    except Exception:
        logger.debug("auto-pipe signal failed lane=%s", row.network_key, exc_info=True)
