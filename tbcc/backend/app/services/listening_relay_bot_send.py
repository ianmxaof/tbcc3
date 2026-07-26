"""Listening relay delivery via loot bot Bot API (no Telethon poster lock)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.channel import Channel
from app.services.listening_relay_send import RelayCopyFollowup, followups_from_json
from app.services.loot_bot_settings_effective import resolve_bot_token_raw
from app.services.telegram_bot_api import tg_post_with_token
from app.services.telegram_custom_emoji import telethon_message_kwargs
from app.utils.telegram_peer import normalize_telethon_peer_identifier

logger = logging.getLogger(__name__)


def _bot_api_text_payload(html: str) -> dict[str, Any]:
    mk = telethon_message_kwargs((html or "").strip(), empty_fallback=" ")
    text = str(mk.get("message") or " ").strip() or " "
    if mk.get("formatting_entities"):
        # Custom emoji entities need Telethon — send plain text (relay templates are mostly HTML links).
        return {"text": text}
    return {"text": text, "parse_mode": "HTML"}


def _inline_keyboard_from_buttons(buttons: list[dict]) -> dict[str, Any] | None:
    row: list[dict[str, str]] = []
    for b in buttons or []:
        t = str(b.get("text") or "").strip()
        u = str(b.get("url") or "").strip()
        if t and u:
            row.append({"text": t, "url": u})
    if not row:
        return None
    return {"inline_keyboard": [row]}


def send_listening_relay_via_bot_api(
    db: Session,
    *,
    channel_id: int,
    html_body: str,
    message_thread_id: int | None,
    send_silent: bool,
    copy_followups_json: str | None,
) -> dict[str, Any]:
    """
    Post relay main HTML + text-only copy follow-ups via Bot API.
    Media follow-ups are skipped (Phase 5b); notes returned in result.
    """
    body = (html_body or "").strip()
    if not body:
        return {"ok": False, "error": "empty_body"}

    token_raw = resolve_bot_token_raw(db)
    if not token_raw:
        return {"ok": False, "error": "loot_bot_token_unset"}

    ch = db.query(Channel).filter(Channel.id == int(channel_id)).first()
    if not ch:
        return {"ok": False, "error": "channel_not_found"}

    chat_id = normalize_telethon_peer_identifier(ch.identifier)
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "disable_web_page_preview": False,
        "disable_notification": bool(send_silent),
        **_bot_api_text_payload(body),
    }
    if message_thread_id:
        payload["message_thread_id"] = int(message_thread_id)

    out = tg_post_with_token("sendMessage", payload, token_raw)
    if not out.get("ok"):
        return out

    result = out.get("result") or {}
    anchor = result.get("message_id")
    notes: list[str] = ["transport=bot_api"]
    followups = followups_from_json(copy_followups_json)
    sent_followups = 0
    skipped_media = 0

    for fu in followups:
        if fu.media_ids or fu.attachment_urls:
            skipped_media += 1
            notes.append("skipped_media_followup")
            continue
        if not (fu.html or "").strip() and not fu.buttons:
            continue
        reply_payload: dict[str, Any] = {
            "chat_id": chat_id,
            "disable_notification": bool(send_silent),
            "disable_web_page_preview": True,
        }
        if message_thread_id:
            reply_payload["message_thread_id"] = int(message_thread_id)
        if anchor:
            reply_payload["reply_to_message_id"] = int(anchor)
        if (fu.html or "").strip():
            reply_payload.update(_bot_api_text_payload(fu.html))
        else:
            reply_payload["text"] = " "
        merged = fu.buttons
        if fu.checkout_stars_enabled:
            notes.append("skipped_checkout_followup_bot_api")
            continue
        kb = _inline_keyboard_from_buttons(merged)
        if kb:
            reply_payload["reply_markup"] = kb
        fo = tg_post_with_token("sendMessage", reply_payload, token_raw)
        if not fo.get("ok"):
            notes.append(f"followup_failed:{fo.get('error')}")
            break
        fr = fo.get("result") or {}
        if fr.get("message_id"):
            anchor = fr["message_id"]
            sent_followups += 1

    if skipped_media:
        notes.append(f"media_followups_deferred={skipped_media}")

    return {
        "ok": True,
        "message_id": anchor,
        "followups_sent": sent_followups,
        "notes": notes,
    }
