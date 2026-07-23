"""Delete Telegram 'X left the group' service messages (shared by secretary / loot / composer).

Requires the bot to be a group admin (or Privacy Mode off). Default: enabled.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def leave_cleanup_enabled() -> bool:
    """Prefer shared flag; fall back to legacy secretary env (default on)."""
    raw = (
        os.getenv("TBCC_CLEAN_LEAVE_MESSAGES")
        or os.getenv("TBCC_SECRETARY_CLEAN_SERVICE_MESSAGES")
        or "1"
    ).strip().lower()
    return raw not in ("0", "false", "no", "off")


def leave_cleanup_chat_allowlist() -> set[int] | None:
    """Optional chat id allowlist. Empty / unset = all groups/supergroups/channels."""
    raw = (os.getenv("TBCC_CLEAN_LEAVE_CHAT_IDS") or "").strip()
    if not raw:
        # Default: prefer Loot Room / MAIN_GROUP when known; still allow all if parse fails.
        try:
            from app.data.aof_network import MAIN_GROUP_IDENT

            mid = int(str(MAIN_GROUP_IDENT).strip())
            # Empty env means all chats — do not restrict to main by default.
            _ = mid
        except Exception:
            pass
        return None
    out: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        p = part.strip()
        if not p:
            continue
        try:
            out.add(int(p))
        except ValueError:
            continue
    return out or None


async def delete_leave_service_message(
    update: Any,
    *,
    bot_label: str = "bot",
) -> bool:
    """
    Delete the update message when it is a left-chat-member service notice.
    Returns True if a delete was attempted successfully.
    """
    if not leave_cleanup_enabled():
        return False
    msg = getattr(update, "effective_message", None) or getattr(update, "message", None)
    chat = getattr(update, "effective_chat", None)
    if not msg or not chat:
        return False
    chat_type = getattr(chat, "type", None)
    if chat_type not in ("group", "supergroup", "channel"):
        return False
    if not getattr(msg, "left_chat_member", None):
        return False
    allow = leave_cleanup_chat_allowlist()
    if allow is not None:
        try:
            if int(chat.id) not in allow:
                return False
        except (TypeError, ValueError):
            return False
    try:
        await msg.delete()
        logger.info(
            "%s leave-message cleanup ok chat=%s user=%s",
            bot_label,
            getattr(chat, "id", None),
            getattr(getattr(msg, "left_chat_member", None), "id", None),
        )
        return True
    except Exception as e:
        logger.warning(
            "%s leave-message cleanup failed chat=%s: %s",
            bot_label,
            getattr(msg, "chat_id", None),
            e,
        )
        try:
            from bots.error_reporter import report_bot_error

            report_bot_error(bot_label, "leave-message cleanup", e)
        except Exception:
            pass
        return False


def register_leave_cleanup_handler(application: Any, *, bot_label: str) -> None:
    """Attach StatusUpdate.LEFT_CHAT_MEMBER handler to a PTB Application."""
    from telegram import Update
    from telegram.ext import ContextTypes, MessageHandler, filters

    async def _on_leave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await delete_leave_service_message(update, bot_label=bot_label)

    application.add_handler(
        MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, _on_leave)
    )
    logger.info(
        "%s leave-message cleanup handler registered (enabled=%s)",
        bot_label,
        leave_cleanup_enabled(),
    )
