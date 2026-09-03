"""Album Composer / Payment bot callback handlers for gatekeeper quarantine review."""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.services.gatekeeper_lane_picker import (
    LANE_BUTTON_SHORT,
    review_lane_picker_keyboard,
    set_picked_lanes,
)
from app.services.gatekeeper_review import (
    html_escape,
    operator_approve_media,
    operator_reject_media,
    parse_review_callback,
)
from app.services.quarantine_batch_review import (
    operator_approve_batch,
    operator_reject_batch,
    operator_route_batch_to_lane,
    parse_batch_review_callback,
)
from app.services.tbcc_telegram_admin import can_operate_storage_hub_bot_api

logger = logging.getLogger(__name__)


def _lane_short(lane: str) -> str:
    return LANE_BUTTON_SHORT.get(lane, (lane or "").upper()[:6]) or lane


async def _edit_batch_card_status(query, *, html: str, clear_keyboard: bool = True) -> None:
    if not query.message:
        return
    try:
        base = getattr(query.message, "text_html", None) or query.message.text or ""
        await query.message.edit_text(
            f"{base}\n\n{html}",
            parse_mode=ParseMode.HTML,
            reply_markup=None if clear_keyboard else query.message.reply_markup,
        )
    except Exception:
        logger.debug("batch card status edit failed", exc_info=True)


async def _refresh_batch_keyboard(query, batch_id: str) -> None:
    """Show ✅ on the selected lane before / while routing."""
    if not query.message:
        return
    try:
        from app.services.quarantine_batch_review import (
            batch_review_keyboard,
            load_batch_payload,
        )

        payload = load_batch_payload(batch_id)
        lead = int(payload.get("lead_media_id") or 0)
        kb = batch_review_keyboard(batch_id, lead, lane_key=payload.get("lane_key"))
        rows = [
            [InlineKeyboardButton(b["text"], callback_data=b["callback_data"]) for b in row]
            for row in kb["inline_keyboard"]
        ]
        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(rows))
    except Exception:
        logger.debug("batch lane picker refresh failed batch=%s", batch_id, exc_info=True)


async def on_gatekeeper_review_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """Handle gk:a:{id} / gk:r:{id} / gk:t:{id}:{lane} / gk:bt:… Returns True if handled."""
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
        batch_action = batch_parsed[0]
        batch_id = batch_parsed[1]
        operator_id = getattr(update.effective_user, "id", None)

        if batch_action == "toggle_lane":
            lane = str(batch_parsed[2]).strip().lower()
            short = _lane_short(lane)
            await query.answer(f"Routing → {short}…", show_alert=False)
            # Stamp pick so keyboard shows ✅, then approve+route the whole batch.
            from app.services.quarantine_batch_review import fanout_batch_lane_picks

            fanout_batch_lane_picks(batch_id, [lane])
            await _refresh_batch_keyboard(query, batch_id)
            with SessionLocal() as db:
                result = operator_route_batch_to_lane(
                    db, batch_id, lane, operator_id=operator_id
                )
            if not result.get("ok"):
                await _edit_batch_card_status(
                    query,
                    html=f"<b>Route failed</b> → {html_escape(short)} "
                    f"(<code>{html_escape(str(result.get('reason') or 'error'))}</code>)",
                )
                return True
            count = result.get("approved") or result.get("total") or 0
            route_fail = int(result.get("route_enqueue_failures") or 0)
            done = (
                f"<b>Routed → {html_escape(short)}</b> · batch "
                f"<code>{html_escape(batch_id)}</code> ({count} item(s))"
            )
            if route_fail:
                done += f"\n⚠️ <b>{route_fail}</b> Celery route enqueue failed"
            await _edit_batch_card_status(query, html=done, clear_keyboard=True)
            return True

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
        route_fail = int(result.get("route_enqueue_failures") or 0)
        alert = f"{label} batch {batch_id} ({count} items)"
        if route_fail:
            alert = f"{alert} — {route_fail} route enqueue FAILED (check logs)"
        await query.answer(alert, show_alert=bool(route_fail))
        if query.message:
            try:
                suffix = f"\n\n<b>{label}</b> batch <code>{html_escape(batch_id)}</code> ({count} items)"
                if route_fail:
                    suffix += f"\n⚠️ <b>{route_fail}</b> item(s) approved but Celery route enqueue failed"
                base = getattr(query.message, "text_html", None) or query.message.text or ""
                await query.message.edit_text(
                    f"{base}{suffix}", parse_mode=ParseMode.HTML, reply_markup=None
                )
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
        # One-tap on single-item cards: stamp lane + approve+route immediately.
        lane = str(parsed[2]).strip().lower()
        short = _lane_short(lane)
        await query.answer(f"Routing → {short}…", show_alert=False)
        set_picked_lanes(media_id, [lane])
        if query.message:
            try:
                from app.models.media import Media
                from app.services.gatekeeper_review import resolve_media_lane_key

                with SessionLocal() as db:
                    media = db.query(Media).filter(Media.id == media_id).first()
                    default_lane = resolve_media_lane_key(db, media) if media else None
                kb = review_lane_picker_keyboard(
                    media_id,
                    [lane],
                    default_lane_key=default_lane,
                )
                rows = [
                    [InlineKeyboardButton(b["text"], callback_data=b["callback_data"]) for b in row]
                    for row in kb["inline_keyboard"]
                ]
                await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(rows))
            except Exception:
                logger.debug("lane picker keyboard refresh failed media_id=%s", media_id, exc_info=True)

        operator_id = getattr(update.effective_user, "id", None)
        with SessionLocal() as db:
            result = operator_approve_media(
                db, media_id, operator_id=operator_id, lane_keys=[lane]
            )
        if result.get("ok"):
            extra = ""
            if result.get("route_enqueue_ok") is False:
                extra = " · ⚠️ route enqueue FAILED"
            suffix = f"\n\n<b>Routed → {html_escape(short)}</b>{extra}"
        else:
            suffix = (
                f"\n\n<b>Route failed</b> → {html_escape(short)} "
                f"(<code>{html_escape(str(result.get('reason') or 'error'))}</code>)"
            )
        if query.message:
            try:
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
                logger.debug("gatekeeper one-tap edit failed media_id=%s", media_id, exc_info=True)
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
    if action == "approve" and result.get("route_enqueue_ok") is False:
        extra = f"{extra} · ⚠️ route enqueue FAILED"
    await query.answer(
        f"{label} #{media_id}{extra}",
        show_alert=bool(action == "approve" and result.get("route_enqueue_ok") is False),
    )

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
