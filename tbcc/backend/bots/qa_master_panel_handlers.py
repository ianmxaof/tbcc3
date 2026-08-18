"""Q&A master panel callbacks (payment bot)."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.data.aof_storage_hub_map import GATEKEEPER_REVIEW_TOPIC_ID
from app.database.session import SessionLocal
from app.services.hub_intake_policy import set_hub_master_auto_approve
from app.services.qa_master_panel import (
    CALLBACK_PREFIX,
    format_qa_master_panel_html,
    queue_lane_deposit_from_master,
)
from app.services.storage_auto_pipe import set_all_lanes_auto_pipe
from app.services.storage_deposit_control import (
    adjust_deposit_limit,
    cycle_deposit_media_types,
    set_deposit_limit,
)
from app.services.storage_topic_deposit import format_deposit_error_text, storage_hub_chat_id_int
from app.services.tbcc_telegram_admin import can_operate_storage_hub_bot_api

logger = logging.getLogger(__name__)


def _forum_context_from_message(msg) -> tuple[bool, int | None]:
    if not msg or not getattr(msg, "chat", None):
        return False, None
    if int(msg.chat.id) != storage_hub_chat_id_int():
        return False, None
    from app.utils.telegram_forum import bot_api_incoming_forum_thread_id

    # Q&A is forum topic 1 (renamed General): Bot API omits message_thread_id.
    return True, bot_api_incoming_forum_thread_id(getattr(msg, "message_thread_id", None))


def _storage_hub_forum_context(update: Update) -> tuple[bool, int | None]:
    """Allow master panel callbacks in any Storage Hub forum subtopic."""
    msg = update.effective_message
    query = update.callback_query
    if query and query.message:
        msg = query.message
    return _forum_context_from_message(msg)


def _in_qa_master_topic(update: Update) -> bool:
    ok, tid = _storage_hub_forum_context(update)
    if not ok or tid is None:
        return False
    return int(tid) == int(GATEKEEPER_REVIEW_TOPIC_ID or 1)


def _parse_page(data: str) -> int:
    if data.startswith(f"{CALLBACK_PREFIX}refresh:"):
        try:
            return max(0, int(data.split(":", 2)[-1]))
        except ValueError:
            return 0
    if data.startswith(f"{CALLBACK_PREFIX}page:"):
        try:
            return max(0, int(data.split(":", 2)[-1]))
        except ValueError:
            return 0
    return 0


async def _refresh_panel(query, bot, *, page: int = 0, note: str = "") -> None:
    if not query.message:
        return
    ok, thread_id = _forum_context_from_message(query.message)
    if not ok or thread_id is None:
        return
    from app.services.qa_master_panel import ensure_qa_master_panel_at_thread

    if note:
        with SessionLocal() as db:
            _ = format_qa_master_panel_html(db, page=page)
    await ensure_qa_master_panel_at_thread(
        bot,
        chat_id=int(query.message.chat_id),
        message_thread_id=int(thread_id),
        page=page,
        force_new=True,
    )


async def cmd_qa_master_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not can_operate_storage_hub_bot_api(update):
        msg = update.effective_message
        if msg:
            await msg.reply_text("Admin only — /qapanel requires operator admin ids in tbcc/.env.")
        return
    if not _in_qa_master_topic(update):
        msg = update.effective_message
        if msg:
            await msg.reply_text("❌ /qapanel only works inside Q&A | APPROVE / DENY | INTAKE.")
        return
    from app.services.qa_master_panel import ensure_qa_master_panel

    out = await ensure_qa_master_panel(context.bot, force_new=False)
    msg = update.effective_message
    if msg:
        await msg.reply_text(f"🟡 Q&A master panel {out.get('action', 'updated')}.")


async def on_qa_master_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    if not query or not query.data or not str(query.data).startswith(CALLBACK_PREFIX):
        return False
    if not can_operate_storage_hub_bot_api(update):
        await query.answer("Admin only", show_alert=True)
        return True
    ok, _thread_id = _storage_hub_forum_context(update)
    if not ok:
        await query.answer("Open a Storage Hub forum subtopic first", show_alert=True)
        return True

    data = str(query.data)
    page = _parse_page(data)
    note = ""

    if data == f"{CALLBACK_PREFIX}noop":
        await query.answer()
        return True
    if data.startswith(f"{CALLBACK_PREFIX}refresh:") or data.startswith(f"{CALLBACK_PREFIX}page:"):
        note = "Refreshed"
        await query.answer(note)
        await _refresh_panel(query, context.bot, page=page, note=note)
        return True
    if data == f"{CALLBACK_PREFIX}review":
        from bots.review_control_handlers import cmd_review

        await query.answer("Review panel")
        await cmd_review(update, context)
        return True
    if data == f"{CALLBACK_PREFIX}apall:on":
        set_all_lanes_auto_pipe(True)
        note = "Auto-pipe ALL lanes ON"
        await query.answer(note)
    elif data == f"{CALLBACK_PREFIX}apall:off":
        set_all_lanes_auto_pipe(False)
        note = "Auto-pipe ALL lanes OFF"
        await query.answer(note)
    elif data == f"{CALLBACK_PREFIX}aapr:on":
        set_hub_master_auto_approve(True)
        note = "Auto-approve ON → pool"
        await query.answer(note)
    elif data == f"{CALLBACK_PREFIX}aapr:off":
        set_hub_master_auto_approve(False)
        note = "Auto-approve OFF → Q&A review"
        await query.answer(note)
    elif data == f"{CALLBACK_PREFIX}lim:-1":
        note = f"Deposit count → {adjust_deposit_limit(-1)}"
        await query.answer(note)
    elif data == f"{CALLBACK_PREFIX}lim:+1":
        note = f"Deposit count → {adjust_deposit_limit(1)}"
        await query.answer(note)
    elif data == f"{CALLBACK_PREFIX}mt:-1":
        note = f"Media type → {cycle_deposit_media_types(-1)}"
        await query.answer(note)
    elif data == f"{CALLBACK_PREFIX}mt:+1":
        note = f"Media type → {cycle_deposit_media_types(1)}"
        await query.answer(note)
    elif data.startswith(f"{CALLBACK_PREFIX}preset:"):
        try:
            lim = int(data.split(":", 2)[-1])
        except ValueError:
            await query.answer("Unknown preset", show_alert=True)
            return True
        set_deposit_limit(lim)
        note = f"Deposit preset → {lim}"
        await query.answer(note)
    elif data.startswith(f"{CALLBACK_PREFIX}dep:"):
        lane = data.split(":", 2)[-1].strip().lower()
        await query.answer(f"Queuing {lane} deposit…")
        with SessionLocal() as db:
            report = queue_lane_deposit_from_master(db, lane)
        if query.message:
            if report.get("ok"):
                await query.message.reply_text(
                    f"📥 Queued <code>{lane}</code> deposit — job {report.get('job_id') or '?'}"
                    + (" · Q&A review path" if report.get("qa_review_only") else ""),
                    parse_mode=ParseMode.HTML,
                )
                try:
                    from app.data.aof_storage_hub_map import storage_map_by_key
                    from app.services.hub_panel_activity import repost_panels_after_deposit

                    row = storage_map_by_key().get(lane)
                    if row:
                        await repost_panels_after_deposit(
                            context.bot,
                            chat_id=int(query.message.chat_id),
                            message_thread_id=int(row.message_thread_id),
                            topic_title=row.topic_title,
                            network_key=lane,
                        )
                    await repost_panels_after_deposit(
                        context.bot,
                        chat_id=int(query.message.chat_id),
                        message_thread_id=int(query.message.message_thread_id or 0),
                        topic_title="Q&A master",
                        network_key=None,
                    )
                except Exception:
                    logger.debug("master deposit panel repost skipped", exc_info=True)
            else:
                await query.message.reply_text(format_deposit_error_text(report))
        await _refresh_panel(query, context.bot, page=page)
        return True
    elif data == f"{CALLBACK_PREFIX}flush:qa":
        from app.data.aof_storage_hub_map import CONTENT_LANE_NETWORK_KEYS
        from app.services.quarantine_batch_review import flush_lane_quarantine_buffer

        flushed = 0
        with SessionLocal() as db:
            for lane in CONTENT_LANE_NETWORK_KEYS:
                if lane in ("inbox", "packs"):
                    continue
                out = flush_lane_quarantine_buffer(db, lane, force=True)
                if out.get("ok") and not out.get("skipped"):
                    flushed += 1
        note = f"Flushed Q&A buffers ({flushed} lane(s))"
        await query.answer(note)
    elif data == f"{CALLBACK_PREFIX}flush:hub":
        from app.workers.storage_hub_album_worker import flush_storage_hub_album_buffers_task

        flush_storage_hub_album_buffers_task.delay(force=True)
        note = "Queued hub album flush"
        await query.answer(note)
    elif data == f"{CALLBACK_PREFIX}flush:vault":
        from app.workers.sent_cache_flush_worker import flush_sent_cache_emoji_buffers_task

        flush_sent_cache_emoji_buffers_task.delay(force=True)
        note = "Queued vault staging flush"
        await query.answer(note)
    elif data == f"{CALLBACK_PREFIX}run:inbox":
        from app.workers.inbox_intake_worker import run_inbox_intake_now

        run_inbox_intake_now.delay()
        note = "Queued inbox deposit"
        await query.answer(note)
    else:
        await query.answer("Unknown action", show_alert=True)
        return True

    await _refresh_panel(query, context.bot, page=page, note=note)
    return True
