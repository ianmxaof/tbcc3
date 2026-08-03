"""Payment bot — /review panel for gatekeeper quarantine bulk approve."""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.services.gatekeeper_review import (
    count_quarantine_waiting,
    format_review_panel_html,
    parse_panel_callback,
    review_panel_confirm_keyboard,
    review_panel_keyboard,
)
from app.services.tbcc_telegram_admin import can_operate_storage_hub_bot_api

logger = logging.getLogger(__name__)

CALLBACK_PREFIX = "gk:p:"


def _panel_markup(
    waiting: int,
    *,
    confirm: bool = False,
    lane_key: str | None = None,
) -> InlineKeyboardMarkup:
    kb = (
        review_panel_confirm_keyboard(waiting=waiting, lane_key=lane_key)
        if confirm
        else review_panel_keyboard(waiting=waiting, lane_key=lane_key)
    )
    rows = [
        [InlineKeyboardButton(b["text"], callback_data=b["callback_data"]) for b in row]
        for row in kb.get("inline_keyboard") or []
    ]
    return InlineKeyboardMarkup(rows)


async def cmd_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not can_operate_storage_hub_bot_api(update):
        msg = update.effective_message
        if msg:
            await msg.reply_text("Admin only — /review requires operator admin ids in tbcc/.env.")
        return
    msg = update.effective_message
    if not msg:
        return
    with SessionLocal() as db:
        waiting = count_quarantine_waiting(db)
        text = format_review_panel_html(db)
    await msg.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=_panel_markup(waiting),
        disable_web_page_preview=True,
    )


async def on_review_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    if not query or not query.data or not str(query.data).startswith(CALLBACK_PREFIX):
        return False
    if not can_operate_storage_hub_bot_api(update):
        await query.answer("Admin only", show_alert=True)
        return True

    parsed = parse_panel_callback(str(query.data))
    if not parsed:
        await query.answer("Unknown action", show_alert=True)
        return True

    action, lane_key = parsed
    operator_id = getattr(update.effective_user, "id", None)

    if action == "open":
        with SessionLocal() as db:
            waiting = count_quarantine_waiting(db, lane_key=lane_key)
            text = format_review_panel_html(db, lane_key=lane_key)
        label = f"{lane_key} lane" if lane_key else "Review panel"
        await query.answer(label)
        if query.message:
            await query.message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=_panel_markup(waiting, lane_key=lane_key),
                disable_web_page_preview=True,
            )
        return True

    if action in ("refresh", "cancel"):
        with SessionLocal() as db:
            waiting = count_quarantine_waiting(db, lane_key=lane_key)
            text = format_review_panel_html(db, lane_key=lane_key)
        await query.answer("Refreshed" if action == "refresh" else "Cancelled")
        if query.message:
            try:
                await query.message.edit_text(
                    text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=_panel_markup(waiting, lane_key=lane_key),
                    disable_web_page_preview=True,
                )
            except Exception:
                logger.debug("review panel refresh failed", exc_info=True)
        return True

    if action == "approve":
        with SessionLocal() as db:
            waiting = count_quarantine_waiting(db, lane_key=lane_key)
            text = format_review_panel_html(db, lane_key=lane_key)
        if waiting < 1:
            await query.answer("Nothing waiting", show_alert=True)
            return True
        lane_note = f" ({lane_key})" if lane_key else ""
        await query.answer(f"Confirm bulk approve{lane_note}")
        if query.message:
            try:
                await query.message.edit_text(
                    f"{text}\n\n<b>Approve all {waiting} waiting item(s){lane_note}?</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=_panel_markup(waiting, confirm=True, lane_key=lane_key),
                    disable_web_page_preview=True,
                )
            except Exception:
                logger.debug("review panel confirm prompt failed", exc_info=True)
        return True

    if action == "approve_yes":
        from app.workers.gatekeeper_review_worker import bulk_approve_waiting_task

        with SessionLocal() as db:
            waiting = count_quarantine_waiting(db, lane_key=lane_key)
        if waiting < 1:
            await query.answer("Nothing waiting", show_alert=True)
            return True
        lane_arg = lane_key or ""
        try:
            bulk_approve_waiting_task.delay(int(operator_id or 0), lane_arg)
            lane_note = f" {lane_key}" if lane_key else ""
            note = f"Queued bulk approve{lane_note} for up to {waiting} item(s)"
        except Exception:
            from app.services.gatekeeper_review import operator_approve_all_waiting

            with SessionLocal() as db:
                result = operator_approve_all_waiting(
                    db,
                    operator_id=operator_id,
                    lane_key=lane_key,
                )
            note = (
                f"Approved {result.get('approved', 0)}"
                f" (skipped {result.get('skipped', 0)})"
            )
        await query.answer(note, show_alert=True)
        if query.message:
            with SessionLocal() as db:
                text = format_review_panel_html(db, lane_key=lane_key)
                new_waiting = count_quarantine_waiting(db, lane_key=lane_key)
            try:
                await query.message.edit_text(
                    f"{text}\n\n<b>{note}</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=_panel_markup(new_waiting, lane_key=lane_key),
                    disable_web_page_preview=True,
                )
            except Exception:
                logger.debug("review panel post-approve refresh failed", exc_info=True)
        return True

    await query.answer("Unknown action", show_alert=True)
    return True
