"""Payment bot — /intake control panel for batch cadence + inbox flush."""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.services.intake_scheduler import (
    adjust_album_size,
    adjust_batch_size,
    adjust_interval_minutes,
    format_status_text,
    get_album_size,
    get_batch_size,
    get_interval_minutes,
)
from app.services.storage_auto_pipe import (
    format_auto_pipe_status,
    set_storage_auto_pipe_enabled,
    storage_auto_pipe_enabled,
)
from app.services.tbcc_telegram_admin import can_operate_storage_hub_bot_api

logger = logging.getLogger(__name__)

CALLBACK_PREFIX = "intake:"


def intake_control_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("Batch +5", callback_data=f"{CALLBACK_PREFIX}batch:+5"),
            InlineKeyboardButton("+10", callback_data=f"{CALLBACK_PREFIX}batch:+10"),
            InlineKeyboardButton("+25", callback_data=f"{CALLBACK_PREFIX}batch:+25"),
        ],
        [
            InlineKeyboardButton("Interval +5m", callback_data=f"{CALLBACK_PREFIX}interval:+5"),
            InlineKeyboardButton("+15m", callback_data=f"{CALLBACK_PREFIX}interval:+15"),
            InlineKeyboardButton("+30m", callback_data=f"{CALLBACK_PREFIX}interval:+30"),
        ],
        [
            InlineKeyboardButton("Album +1", callback_data=f"{CALLBACK_PREFIX}album:+1"),
            InlineKeyboardButton("+2", callback_data=f"{CALLBACK_PREFIX}album:+2"),
            InlineKeyboardButton("+3", callback_data=f"{CALLBACK_PREFIX}album:+3"),
        ],
        [
            InlineKeyboardButton("▶ Run all due lanes", callback_data=f"{CALLBACK_PREFIX}run:all"),
            InlineKeyboardButton("▶ Inbox now", callback_data=f"{CALLBACK_PREFIX}run:inbox"),
        ],
        [
            InlineKeyboardButton("📤 Flush inbox albums", callback_data=f"{CALLBACK_PREFIX}flush:inbox"),
            InlineKeyboardButton("📦 Flush hub albums", callback_data=f"{CALLBACK_PREFIX}flush:hub"),
        ],
        [
            InlineKeyboardButton("📦 Post vault staging", callback_data=f"{CALLBACK_PREFIX}flush:sentcache"),
        ],
    ]
    if storage_auto_pipe_enabled():
        rows.append(
            [InlineKeyboardButton("⏸ Auto-pipe OFF", callback_data=f"{CALLBACK_PREFIX}autopipe:off")]
        )
    else:
        rows.append(
            [InlineKeyboardButton("▶ Auto-pipe ON", callback_data=f"{CALLBACK_PREFIX}autopipe:on")]
        )
    return InlineKeyboardMarkup(rows)


async def cmd_intake(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not can_operate_storage_hub_bot_api(update):
        msg = update.effective_message
        if msg:
            await msg.reply_text("Admin only — /intake requires operator admin ids in tbcc/.env.")
        return
    msg = update.effective_message
    if not msg:
        return
    text = (
        f"{format_status_text()}\n\n"
        f"{format_auto_pipe_status()}\n\n"
        f"<i>Batch {get_batch_size()} · interval {get_interval_minutes()}m · album {get_album_size()}</i>"
    )
    await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=intake_control_keyboard())


async def on_intake_control_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    if not query or not query.data or not str(query.data).startswith(CALLBACK_PREFIX):
        return False
    if not can_operate_storage_hub_bot_api(update):
        await query.answer("Admin only", show_alert=True)
        return True

    action = str(query.data)[len(CALLBACK_PREFIX) :]
    note = ""

    if action.startswith("batch:"):
        delta = int(action.split(":", 1)[1])
        val = adjust_batch_size(delta)
        note = f"Global batch → {val}"
    elif action.startswith("interval:"):
        delta = int(action.split(":", 1)[1])
        val = adjust_interval_minutes(delta)
        note = f"Global interval → {val}m"
    elif action.startswith("album:"):
        delta = int(action.split(":", 1)[1])
        val = adjust_album_size(delta)
        note = f"Inbox album size → {val}"
    elif action == "run:all":
        from app.workers.inbox_intake_worker import run_intake_schedule_tick

        run_intake_schedule_tick.delay(force=True)
        note = "Queued intake tick (all due lanes, force)"
    elif action == "run:inbox":
        from app.workers.inbox_intake_worker import run_inbox_intake_now

        run_inbox_intake_now.delay()
        note = "Queued inbox deposit + album flush"
    elif action == "flush:inbox":
        from app.workers.inbox_intake_worker import flush_inbox_quarantine_albums

        flush_inbox_quarantine_albums.delay(force=True)
        note = "Queued inbox quarantine album flush"
    elif action == "flush:hub":
        from app.workers.storage_hub_album_worker import flush_storage_hub_album_buffers_task

        flush_storage_hub_album_buffers_task.delay(force=True)
        note = "Queued Storage Hub album buffer flush"
    elif action == "flush:sentcache":
        from app.workers.sent_cache_flush_worker import flush_sent_cache_emoji_buffers_task

        flush_sent_cache_emoji_buffers_task.delay(force=True)
        note = "Queued SENT VAULT staging album post (does not delete vault media)"
    elif action == "autopipe:on":
        set_storage_auto_pipe_enabled(True)
        note = "Auto-pipe ON"
    elif action == "autopipe:off":
        set_storage_auto_pipe_enabled(False)
        note = "Auto-pipe OFF"
    else:
        await query.answer("Unknown action", show_alert=True)
        return True

    await query.answer(note or "Updated", show_alert=False)
    if query.message:
        text = (
            f"{format_status_text()}\n\n"
            f"{format_auto_pipe_status()}\n\n"
            f"<i>Batch {get_batch_size()} · interval {get_interval_minutes()}m · album {get_album_size()}</i>\n"
            f"<b>{note}</b>"
        )
        try:
            await query.message.edit_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=intake_control_keyboard(),
            )
        except Exception:
            logger.debug("intake panel refresh failed", exc_info=True)
    return True
