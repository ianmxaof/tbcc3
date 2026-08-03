"""Storage Hub /depositpanel — preset limits + media-type toggles."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.data.aof_storage_hub_map import INBOX_CHANNEL_IDENT
from app.services.storage_deposit_control import (
    adjust_deposit_limit,
    cycle_deposit_media_types,
    deposit_control_inline_markup,
    format_deposit_panel_html,
    get_deposit_limit,
    get_deposit_media_types,
    set_deposit_limit,
)
from app.services.storage_topic_deposit import resolve_storage_topic_row, storage_hub_chat_id_int
from app.services.tbcc_telegram_admin import can_operate_storage_hub_bot_api

logger = logging.getLogger(__name__)

CALLBACK_PREFIX = "depctl:"


def _in_storage_hub_context(update: Update) -> tuple[bool, int | None, str | None]:
    """Return (ok, thread_id, topic_title) when update is in a mapped hub topic or inbox channel."""
    chat = update.effective_chat
    msg = update.effective_message
    query = update.callback_query
    if query and query.message:
        msg = query.message
    if not chat or not msg:
        return False, None, None
    cid = int(chat.id)
    if cid == int(INBOX_CHANNEL_IDENT):
        return True, None, "AOF INBOX #CHANNEL"
    if cid != storage_hub_chat_id_int():
        return False, None, None
    thread_id = getattr(msg, "message_thread_id", None)
    if not thread_id:
        return False, None, None
    row = resolve_storage_topic_row(int(thread_id))
    if not row:
        return False, None, None
    return True, int(thread_id), row.topic_title


async def cmd_deposit_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not can_operate_storage_hub_bot_api(update):
        msg = update.effective_message
        if msg:
            await msg.reply_text("Admin only — /depositpanel requires operator admin ids in tbcc/.env.")
        return
    ok, thread_id, title = _in_storage_hub_context(update)
    msg = update.effective_message
    chat = update.effective_chat
    if not msg or not chat:
        return
    if not ok:
        await msg.reply_text(
            "❌ /depositpanel only works inside Storage Hub forum subtopics or the AOF INBOX channel."
        )
        return
    from app.services.storage_deposit_panel_pins import ensure_storage_deposit_panel

    out = await ensure_storage_deposit_panel(
        context.bot,
        chat_id=int(chat.id),
        message_thread_id=thread_id,
        topic_title=title or "",
        force_new=False,
    )
    if out.get("action") == "edited":
        await msg.reply_text(f"📥 Deposit panel refreshed in this topic ({title or 'lane'}).")
    elif out.get("ok"):
        await msg.reply_text(f"📥 Deposit panel posted and pinned ({title or 'lane'}).")


async def on_deposit_control_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    callback_data: str | None = None,
    embedded: bool = False,
) -> bool:
    query = update.callback_query
    if not query:
        return False
    data = str(callback_data or query.data or "")
    if not data.startswith(CALLBACK_PREFIX):
        return False
    if not can_operate_storage_hub_bot_api(update):
        await query.answer("Admin only", show_alert=True)
        return True

    ok, thread_id, title = _in_storage_hub_context(update)
    if not ok:
        await query.answer("Open a mapped Storage Hub topic first", show_alert=True)
        return True

    note = ""
    if data == f"{CALLBACK_PREFIX}noop":
        await query.answer()
    elif data == f"{CALLBACK_PREFIX}refresh":
        note = "Refreshed"
        await query.answer(note or "OK")
    elif data == f"{CALLBACK_PREFIX}lim:-1":
        val = adjust_deposit_limit(-1)
        note = f"Count → {val}"
        await query.answer(note)
    elif data == f"{CALLBACK_PREFIX}lim:+1":
        val = adjust_deposit_limit(1)
        note = f"Count → {val}"
        await query.answer(note)
    elif data == f"{CALLBACK_PREFIX}mt:-1":
        val = cycle_deposit_media_types(-1)
        note = f"Type → {val}"
        await query.answer(note)
    elif data == f"{CALLBACK_PREFIX}mt:+1":
        val = cycle_deposit_media_types(1)
        note = f"Type → {val}"
        await query.answer(note)
    elif data.startswith(f"{CALLBACK_PREFIX}preset:"):
        try:
            lim = int(data.split(":", 2)[-1])
        except ValueError:
            await query.answer("Unknown preset", show_alert=True)
            return True
        set_deposit_limit(lim)
        note = f"Preset → {lim}"
        await query.answer(note)
    elif data == f"{CALLBACK_PREFIX}run":
        await query.answer("Queuing deposit…")
        await _run_deposit_from_panel(update, context, thread_id=thread_id)
        return True
    else:
        await query.answer()
        return True

    if query.message and not embedded:
        try:
            from app.services.storage_deposit_panel_pins import (
                ensure_storage_deposit_panel,
                get_stored_panel_message_id,
            )

            chat = query.message.chat
            thread_id = getattr(query.message, "message_thread_id", None)
            stored = get_stored_panel_message_id(int(chat.id), thread_id)
            if stored and int(stored) == int(query.message.message_id):
                await ensure_storage_deposit_panel(
                    context.bot,
                    chat_id=int(chat.id),
                    message_thread_id=thread_id,
                    topic_title=title or "",
                    force_new=False,
                )
            else:
                await query.message.edit_text(
                    format_deposit_panel_html(thread_title=title),
                    parse_mode=ParseMode.HTML,
                    reply_markup=deposit_control_inline_markup(),
                )
        except Exception:
            logger.debug("deposit panel refresh failed", exc_info=True)
    return True


async def _run_deposit_from_panel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    thread_id: int | None,
) -> None:
    from bots.storage_hub_deposit_bot import _run_deposit_job

    query = update.callback_query
    if not query or not query.message:
        return
    chat = update.effective_chat
    if not chat:
        return

    limit = get_deposit_limit()
    media_types = get_deposit_media_types()

    if thread_id is None:
        from app.database.session import SessionLocal
        from app.services.storage_topic_deposit import format_deposit_error_text, queue_inbox_channel_deposit

        db = SessionLocal()
        try:
            report = queue_inbox_channel_deposit(db, limit=limit, media_types=media_types)
        finally:
            db.close()
        if not report.get("ok"):
            await query.message.reply_text(format_deposit_error_text(report))
            return
        await query.message.reply_text(
            f"📥 Queued inbox channel deposit — {limit} ({media_types}). "
            f"Job: {report.get('job_id') or '?'}"
        )
        return

    await _run_deposit_job(
        update,
        context,
        message_thread_id=int(thread_id),
        limit=limit,
        media_types=media_types,
        reply_msg=query.message,
    )
