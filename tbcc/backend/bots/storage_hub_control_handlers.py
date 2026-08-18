"""Storage Hub lane + SENT VAULT control panel callbacks (payment bot)."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.data.aof_storage_hub_map import INBOX_CHANNEL_IDENT, SENT_CACHE_TOPIC, GATEKEEPER_REVIEW_TOPIC_ID, GATEKEEPER_REVIEW_TOPIC_TITLE
from app.services.hub_lane_control import (
    set_lane_loot_preview_enabled,
)
from app.services.sent_cache_control import (
    adjust_composer_album_size,
    adjust_preview_max_loot_albums,
    format_sent_cache_panel_html,
    sent_cache_control_keyboard,
    set_composer_enabled,
    set_erome_export_enabled,
    set_main_group_export_enabled,
    composer_enabled,
    erome_export_enabled,
    main_group_export_enabled,
)
from app.services.storage_auto_pipe import set_lane_auto_pipe_enabled
from app.services.storage_deposit_control import (
    adjust_deposit_limit,
    cycle_deposit_media_types,
    set_deposit_limit,
)
from app.services.storage_topic_deposit import resolve_storage_topic_row, storage_hub_chat_id_int
from app.services.storage_sent_cache import storage_sent_cache_topic_id
from app.services.tbcc_telegram_admin import can_operate_storage_hub_bot_api

logger = logging.getLogger(__name__)

HUB_CALLBACK_PREFIX = "hubctl:"
SENT_CACHE_PREFIX = "sctl:"


def _hub_context(update: Update) -> tuple[bool, int | None, str | None, str | None]:
    chat = update.effective_chat
    msg = update.effective_message
    query = update.callback_query
    if query and query.message:
        msg = query.message
    if not chat or not msg:
        return False, None, None, None
    cid = int(chat.id)
    if cid == int(INBOX_CHANNEL_IDENT):
        return True, None, "AOF INBOX #CHANNEL", "inbox"
    if cid != storage_hub_chat_id_int():
        return False, None, None, None
    from app.utils.telegram_forum import bot_api_incoming_forum_thread_id

    # Q&A is forum topic 1 (renamed General): Bot API omits message_thread_id.
    tid = bot_api_incoming_forum_thread_id(getattr(msg, "message_thread_id", None))
    if tid == int(GATEKEEPER_REVIEW_TOPIC_ID or 0):
        return True, tid, GATEKEEPER_REVIEW_TOPIC_TITLE, "qa_master"
    if tid == storage_sent_cache_topic_id():
        return True, tid, SENT_CACHE_TOPIC.topic_title, "sent_cache"
    row = resolve_storage_topic_row(tid)
    if not row:
        return False, None, None, None
    return True, tid, row.topic_title, row.network_key


async def cmd_hubpanel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not can_operate_storage_hub_bot_api(update):
        msg = update.effective_message
        if msg:
            await msg.reply_text("Admin only — /hubpanel requires operator admin ids in tbcc/.env.")
        return
    ok, thread_id, title, kind = _hub_context(update)
    msg = update.effective_message
    if not msg or not ok:
        if msg:
            await msg.reply_text("❌ /hubpanel only works inside mapped Storage Hub subtopics.")
        return

    if kind == "sent_cache":
        from app.services.storage_hub_control_panels import ensure_sent_cache_panel

        out = await ensure_sent_cache_panel(context.bot, force_new=False)
        await msg.reply_text(f"📦 SENT VAULT panel {out.get('action', 'updated')}.")
        return

    if kind == "qa_master":
        from app.services.qa_master_panel import ensure_qa_master_panel

        out = await ensure_qa_master_panel(context.bot, force_new=False)
        await msg.reply_text(f"🟡 Q&A master panel {out.get('action', 'updated')}.")
        return

    if kind == "inbox":
        from app.services.storage_hub_control_panels import ensure_inbox_intake_panel

        out = await ensure_inbox_intake_panel(context.bot, force_new=False)
        await msg.reply_text(f"📥 Inbox intake panel {out.get('action', 'updated')}.")
        return

    from app.services.storage_deposit_panel_pins import ensure_storage_deposit_panel

    out = await ensure_storage_deposit_panel(
        context.bot,
        chat_id=int(msg.chat_id),
        message_thread_id=thread_id,
        topic_title=title or "",
        force_new=False,
    )
    await msg.reply_text(f"📥 Lane panel {out.get('action', 'updated')} ({title or 'lane'}).")


async def on_hub_lane_control_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    if not query or not query.data or not str(query.data).startswith(HUB_CALLBACK_PREFIX):
        return False
    if not can_operate_storage_hub_bot_api(update):
        await query.answer("Admin only", show_alert=True)
        return True

    ok, thread_id, title, network_key = _hub_context(update)
    if not ok or not thread_id:
        await query.answer("Open a mapped Storage Hub topic first", show_alert=True)
        return True

    data = str(query.data)[len(HUB_CALLBACK_PREFIX) :]
    note = ""

    if data == "noop":
        await query.answer()
    elif data == "refresh":
        note = "Refreshed"
        await query.answer(note)
    elif data == "lim:-1":
        note = f"Count → {adjust_deposit_limit(-1)}"
        await query.answer(note)
    elif data == "lim:+1":
        note = f"Count → {adjust_deposit_limit(1)}"
        await query.answer(note)
    elif data == "mt:-1":
        note = f"Type → {cycle_deposit_media_types(-1)}"
        await query.answer(note)
    elif data == "mt:+1":
        note = f"Type → {cycle_deposit_media_types(1)}"
        await query.answer(note)
    elif data.startswith("preset:"):
        try:
            lim = int(data.split(":", 1)[1])
        except ValueError:
            await query.answer("Unknown preset", show_alert=True)
            return True
        set_deposit_limit(lim)
        note = f"Preset → {lim}"
        await query.answer(note)
    elif data == "deposit":
        await query.answer("Queuing deposit…")
        from bots.storage_deposit_control_handlers import _run_deposit_from_panel

        await _run_deposit_from_panel(
            update,
            context,
            thread_id=thread_id,
            repost_panels=True,
        )
        return True
    elif data.startswith("autopipe:"):
        parts = data.split(":")
        if len(parts) != 3:
            await query.answer("Bad action", show_alert=True)
            return True
        enabled = parts[1] == "on"
        lane = parts[2]
        set_lane_auto_pipe_enabled(lane, enabled)
        note = f"Auto-pipe {'ON' if enabled else 'OFF'} ({lane})"
        await query.answer(note)
    elif data.startswith("preview:"):
        parts = data.split(":")
        if len(parts) != 3:
            await query.answer("Bad action", show_alert=True)
            return True
        enabled = parts[1] == "on"
        lane = parts[2]
        set_lane_loot_preview_enabled(lane, enabled)
        note = f"Loot preview {'ON' if enabled else 'OFF'} ({lane})"
        await query.answer(note)
    elif data == "master":
        from app.services.qa_master_panel import ensure_qa_master_panel_at_thread

        await query.answer("Master panel → bottom")
        await ensure_qa_master_panel_at_thread(
            context.bot,
            chat_id=int(query.message.chat_id),
            message_thread_id=int(thread_id),
            force_new=True,
        )
        return True
    elif data == "rebundle:preview":
        from app.services.topic_rebundle_service import (
            format_topic_rebundle_summary,
            rebundle_storage_topic_loose_media_sync,
        )

        report = rebundle_storage_topic_loose_media_sync(
            message_thread_id=int(thread_id),
            dry_run=True,
            allow_partial=True,
            delete_sources=True,
        )
        summary = format_topic_rebundle_summary(report, html=False)
        await query.answer(summary[:200], show_alert=True)
        return True
    elif data == "rebundle:run":
        from app.workers.topic_rebundle_worker import rebundle_storage_topic_task

        rebundle_storage_topic_task.delay(
            message_thread_id=int(thread_id),
            dry_run=False,
            allow_partial=True,
            delete_sources=True,
        )
        await query.answer("Queued rebundle (partial OK; delete sources)")
        return True
    else:
        await query.answer()
        return True

    if query.message:
        try:
            from app.services.hub_panel_activity import repost_panels_after_deposit

            await repost_panels_after_deposit(
                context.bot,
                chat_id=int(query.message.chat_id),
                message_thread_id=thread_id,
                topic_title=title or "",
                network_key=network_key,
            )
        except Exception:
            logger.debug("hub lane panel refresh failed", exc_info=True)
    return True


async def on_sent_cache_control_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    if not query or not query.data or not str(query.data).startswith(SENT_CACHE_PREFIX):
        return False
    if not can_operate_storage_hub_bot_api(update):
        await query.answer("Admin only", show_alert=True)
        return True

    ok, thread_id, _title, kind = _hub_context(update)
    if not ok or kind != "sent_cache":
        await query.answer("Open the SENT VAULT topic first", show_alert=True)
        return True

    data = str(query.data)[len(SENT_CACHE_PREFIX) :]
    note = ""

    if data == "noop":
        await query.answer()
    elif data == "refresh":
        note = "Refreshed"
        await query.answer(note)
    elif data == "composer:toggle":
        set_composer_enabled(not composer_enabled())
        note = f"Composer {'ON' if composer_enabled() else 'OFF'}"
        await query.answer(note)
    elif data == "main:toggle":
        set_main_group_export_enabled(not main_group_export_enabled())
        note = f"Loot preview {'ON' if main_group_export_enabled() else 'OFF'}"
        await query.answer(note)
    elif data == "erome:toggle":
        set_erome_export_enabled(not erome_export_enabled())
        note = f"Erome {'ON' if erome_export_enabled() else 'OFF'}"
        await query.answer(note)
    elif data == "preview:-1":
        note = f"Preview cap → {adjust_preview_max_loot_albums(-1)}"
        await query.answer(note)
    elif data == "preview:+1":
        note = f"Preview cap → {adjust_preview_max_loot_albums(1)}"
        await query.answer(note)
    elif data == "album:-1":
        note = f"Album size → {adjust_composer_album_size(-1)}"
        await query.answer(note)
    elif data == "album:+1":
        note = f"Album size → {adjust_composer_album_size(1)}"
        await query.answer(note)
    elif data == "flush":
        from app.workers.sent_cache_flush_worker import flush_sent_cache_emoji_buffers_task

        flush_sent_cache_emoji_buffers_task.delay(force=True)
        note = "Queued vault staging flush"
        await query.answer(note)
    else:
        await query.answer()
        return True

    if query.message:
        try:
            await query.message.edit_text(
                format_sent_cache_panel_html(),
                parse_mode=ParseMode.HTML,
                reply_markup=sent_cache_control_keyboard(),
            )
        except Exception:
            logger.debug("sent cache panel refresh failed", exc_info=True)
    return True
