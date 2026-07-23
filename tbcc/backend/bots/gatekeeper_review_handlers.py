"""Album Composer callback handlers for gatekeeper quarantine review."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.services.gatekeeper_review import (
    operator_approve_media,
    operator_reject_media,
    parse_review_callback,
)
from app.services.tbcc_telegram_admin import can_operate_storage_hub_bot_api

logger = logging.getLogger(__name__)


async def on_gatekeeper_review_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """Handle gk:a:{id} / gk:r:{id}. Returns True if handled."""
    query = update.callback_query
    if not query:
        return False
    parsed = parse_review_callback(query.data)
    if not parsed:
        return False

    if not can_operate_storage_hub_bot_api(update):
        await query.answer("Admin only", show_alert=True)
        return True

    action, media_id = parsed
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
    await query.answer(f"{label} #{media_id}{extra}")

    if query.message:
        try:
            base = getattr(query.message, "text_html", None) or query.message.text or ""
            await query.message.edit_text(
                f"{base}\n\n<b>{label}</b> by operator.{extra}",
                parse_mode=ParseMode.HTML,
                reply_markup=None,
            )
        except Exception:
            logger.debug("gatekeeper review edit failed media_id=%s", media_id, exc_info=True)
    return True
