"""Album Composer / Payment bot callback handlers for gatekeeper quarantine review."""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.services.gatekeeper_lane_picker import (
    format_lane_pick_hint,
    review_lane_picker_keyboard,
    toggle_picked_lane,
)
from app.services.gatekeeper_review import (
    html_escape,
    operator_approve_media,
    operator_reject_media,
    parse_review_callback,
)
from app.services.inbox_intake_review import (
    operator_approve_batch,
    operator_reject_batch,
    parse_batch_review_callback,
)
from app.services.tbcc_telegram_admin import can_operate_storage_hub_bot_api

logger = logging.getLogger(__name__)


async def on_gatekeeper_review_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """Handle gk:a:{id} / gk:r:{id} / gk:t:{id}:{lane}. Returns True if handled."""
    from bots.review_control_handlers import on_review_panel_callback

    if await on_review_panel_callback(update, context):
        return True

    query = update.callback_query
    if not query:
        return False

    batch_parsed = parse_batch_review_callback(query.data)
    if batch_parsed:
        if not can_operate_storage_hub_bot_api(update):
            await query.answer("Admin only", show_alert=True)
            return True
        batch_action, batch_id = batch_parsed
        operator_id = getattr(update.effective_user, "id", None)
        with SessionLocal() as db:
            if batch_action == "approve":
                result = operator_approve_batch(db, batch_id, operator_id=operator_id)
            else:
                result = operator_reject_batch(db, batch_id, operator_id=operator_id)
        if not result.get("ok"):
            await query.answer(result.get("reason") or "Failed", show_alert=True)
            return True
        label = "Approved" if batch_action == "approve" else "Rejected"
        count = result.get("approved") or result.get("rejected") or result.get("total") or 0
        await query.answer(f"{label} batch {batch_id} ({count} items)")
        if query.message:
            try:
                suffix = f"\n\n<b>{label}</b> batch <code>{html_escape(batch_id)}</code> ({count} items)"
                base = getattr(query.message, "text_html", None) or query.message.text or ""
                await query.message.edit_text(f"{base}{suffix}", parse_mode=ParseMode.HTML, reply_markup=None)
            except Exception:
                logger.debug("batch review edit failed batch=%s", batch_id, exc_info=True)
        return True

    parsed = parse_review_callback(query.data)
    if not parsed:
        return False

    if not can_operate_storage_hub_bot_api(update):
        await query.answer("Admin only", show_alert=True)
        return True

    action = parsed[0]
    media_id = int(parsed[1])

    if action == "toggle_lane":
        lane = str(parsed[2])
        selected = toggle_picked_lane(media_id, lane)
        await query.answer(format_lane_pick_hint(selected), show_alert=False)
        if query.message:
            try:
                kb = review_lane_picker_keyboard(media_id, selected)
                rows = [
                    [InlineKeyboardButton(b["text"], callback_data=b["callback_data"]) for b in row]
                    for row in kb["inline_keyboard"]
                ]
                await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(rows))
            except Exception:
                logger.debug("lane picker keyboard refresh failed media_id=%s", media_id, exc_info=True)
        return True

    operator_id = getattr(update.effective_user, "id", None)

    with SessionLocal() as db:
        if action == "approve":
            result = operator_approve_media(db, media_id, operator_id=operator_id)
        else:
            result = operator_reject_media(db, media_id, operator_id=operator_id)

    if not result.get("ok"):
        await query.answer(result.get("reason") or "Failed", show_alert=True)
        return True

    label = "Approved" if action == "approve" else "Rejected"
    demote = (result.get("demote") or {}) if action == "reject" else {}
    extra = ""
    if demote.get("demoted"):
        extra = f" · source demoted (streak {demote.get('streak')})"
    lanes = result.get("operator_lanes") or []
    if action == "approve" and lanes:
        extra = f"{extra} · {', '.join(lanes)}"
    await query.answer(f"{label} #{media_id}{extra}")

    if query.message:
        try:
            suffix = f"\n\n<b>{label}</b> by operator.{extra}"
            if action == "approve" and lanes:
                suffix = f"\n\n<b>{label}</b> → {html_escape(', '.join(lanes))}{extra}"
            msg = query.message
            has_media = bool(
                msg.caption is not None
                or msg.photo
                or msg.video
                or msg.document
                or msg.animation
            )
            if has_media:
                base = getattr(msg, "caption_html", None) or msg.caption or ""
                await msg.edit_caption(
                    caption=f"{base}{suffix}",
                    parse_mode=ParseMode.HTML,
                    reply_markup=None,
                )
            else:
                base = getattr(msg, "text_html", None) or msg.text or ""
                await msg.edit_text(
                    f"{base}{suffix}",
                    parse_mode=ParseMode.HTML,
                    reply_markup=None,
                )
        except Exception:
            logger.debug("gatekeeper review edit failed media_id=%s", media_id, exc_info=True)
    return True
