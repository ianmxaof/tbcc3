"""Operator quarantine review — Telegram notify + approve/reject actions."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT
from app.services.gatekeeper_source_demote import record_operator_approve, record_operator_reject
from app.services.media_gatekeeper import (
    gatekeeper_verdict_from_media,
    parse_source_channel_id,
)
from app.services.scrape_channel_intel import pool_key_for_pool_id

logger = logging.getLogger(__name__)

CALLBACK_APPROVE = "gk:a:"
CALLBACK_REJECT = "gk:r:"


def review_notify_enabled() -> bool:
    return (os.getenv("TBCC_GATEKEEPER_REVIEW_NOTIFY") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def review_chat_id() -> int:
    raw = (os.getenv("TBCC_GATEKEEPER_REVIEW_CHAT_ID") or STORAGE_HUB_IDENT).strip()
    return int(raw)


def review_thread_id() -> int | None:
    raw = (os.getenv("TBCC_GATEKEEPER_REVIEW_THREAD_ID") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _bot_token() -> str:
    return (
        os.getenv("TBCC_ALBUM_COMPOSER_BOT_TOKEN")
        or os.getenv("BOT_TOKEN")
        or os.getenv("TBCC_PAYMENT_BOT_TOKEN")
        or ""
    ).strip()


def _classification_dict(media: Any) -> dict[str, Any]:
    raw = getattr(media, "classification_json", None)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _merge_operator_action(
    media: Any,
    *,
    action: str,
    operator_id: int | None,
    extra: dict[str, Any] | None = None,
) -> None:
    data = _classification_dict(media)
    gk = data.get("gatekeeper") if isinstance(data.get("gatekeeper"), dict) else {}
    gk = dict(gk)
    gk["verdict"] = "approve" if action == "approve" else "reject"
    gk["operator_action"] = action
    gk["operator_id"] = operator_id
    gk["operator_at"] = datetime.now(timezone.utc).isoformat()
    if extra:
        gk["operator_extra"] = extra
    data["gatekeeper"] = gk
    media.classification_json = json.dumps(data, ensure_ascii=False)


def format_quarantine_review_html(db: Session, media: Any) -> str:
    from app.models.content_pool import ContentPool

    meta = _classification_dict(media).get("gatekeeper") or {}
    score = meta.get("quality_score", "?")
    lane = "?"
    if media.pool_id:
        lane_key, _ = pool_key_for_pool_id(db, int(media.pool_id))
        if lane_key:
            lane = lane_key.upper()
    expected = meta.get("globs", {}).get("lane_fit", {}).get("expected")
    if expected:
        lane = str(expected).upper()
    warnings = meta.get("warnings") or []
    blocks = meta.get("blocks") or []
    flags = warnings + blocks
    flag_line = ", ".join(flags[:4]) if flags else "review"
    src = (media.source_channel or "?")[:80]
    mt = (media.media_type or "media").upper()
    return (
        f"🟡 <b>QUARANTINE</b> #{media.id} · {lane} · score <b>{score}</b>\n"
        f"<code>{mt}</code> · <code>{html_escape(src)}</code>\n"
        f"<i>{html_escape(flag_line)}</i>"
    )


def html_escape(text: str) -> str:
    import html

    return html.escape(str(text or ""), quote=False)


def review_inline_keyboard(media_id: int) -> dict[str, Any]:
    mid = int(media_id)
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Approve", "callback_data": f"{CALLBACK_APPROVE}{mid}"},
                {"text": "🗑 Reject", "callback_data": f"{CALLBACK_REJECT}{mid}"},
            ]
        ]
    }


def parse_review_callback(data: str | None) -> tuple[str, int] | None:
    raw = (data or "").strip()
    if raw.startswith(CALLBACK_APPROVE):
        return ("approve", int(raw[len(CALLBACK_APPROVE) :]))
    if raw.startswith(CALLBACK_REJECT):
        return ("reject", int(raw[len(CALLBACK_REJECT) :]))
    return None


def operator_approve_media(
    db: Session,
    media_id: int,
    *,
    operator_id: int | None = None,
) -> dict[str, Any]:
    from app.models.media import Media

    media = db.query(Media).filter(Media.id == int(media_id)).first()
    if not media:
        return {"ok": False, "reason": "not_found", "media_id": media_id}
    prior = gatekeeper_verdict_from_media(media)
    if prior not in ("quarantine", None) and (media.status or "").lower() == "approved":
        return {"ok": False, "reason": "already_approved", "media_id": media_id}

    media.status = "approved"
    _merge_operator_action(media, action="approve", operator_id=operator_id)
    db.commit()
    record_operator_approve(db, media)
    logger.info("gatekeeper operator approve media_id=%s operator=%s", media_id, operator_id)
    return {"ok": True, "media_id": media_id, "status": "approved"}


def operator_reject_media(
    db: Session,
    media_id: int,
    *,
    operator_id: int | None = None,
) -> dict[str, Any]:
    from app.models.media import Media

    media = db.query(Media).filter(Media.id == int(media_id)).first()
    if not media:
        return {"ok": False, "reason": "not_found", "media_id": media_id}

    media.status = "rejected"
    demote_info = record_operator_reject(db, media)
    _merge_operator_action(
        media,
        action="reject",
        operator_id=operator_id,
        extra=demote_info,
    )
    db.commit()
    logger.info(
        "gatekeeper operator reject media_id=%s operator=%s streak=%s demoted=%s",
        media_id,
        operator_id,
        demote_info.get("streak"),
        demote_info.get("demoted"),
    )
    return {
        "ok": True,
        "media_id": media_id,
        "status": "rejected",
        "demote": demote_info,
    }


def send_quarantine_review_message(db: Session, media_id: int) -> dict[str, Any]:
    """Post review card to configured Telegram chat (sync HTTP)."""
    from app.models.media import Media

    if not review_notify_enabled():
        return {"ok": False, "skipped": True, "reason": "notify_disabled"}

    token = _bot_token()
    if not token:
        return {"ok": False, "reason": "bot_token_unset"}

    media = db.query(Media).filter(Media.id == int(media_id)).first()
    if not media:
        return {"ok": False, "reason": "not_found"}
    if gatekeeper_verdict_from_media(media) != "quarantine":
        return {"ok": False, "reason": "not_quarantine"}

    text = format_quarantine_review_html(db, media)
    payload: dict[str, Any] = {
        "chat_id": review_chat_id(),
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": review_inline_keyboard(media_id),
        "disable_web_page_preview": True,
    }
    tid = review_thread_id()
    if tid:
        payload["message_thread_id"] = int(tid)

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with httpx.Client(timeout=20) as client:
            r = client.post(url, json=payload)
            data = r.json() if r.content else {}
            if r.status_code != 200 or not data.get("ok"):
                return {"ok": False, "error": str(data)[:400]}
            result = data.get("result") or {}
            return {
                "ok": True,
                "media_id": media_id,
                "message_id": result.get("message_id"),
                "chat_id": result.get("chat", {}).get("id"),
            }
    except Exception as e:
        logger.warning("quarantine review send failed media_id=%s: %s", media_id, e)
        return {"ok": False, "error": str(e)[:300]}


def enqueue_quarantine_review(media_id: int) -> None:
    """Queue Telegram review card (non-blocking)."""
    if not review_notify_enabled():
        return
    try:
        from app.workers.gatekeeper_review_worker import send_quarantine_review_task

        send_quarantine_review_task.delay(int(media_id))
    except Exception:
        logger.debug("quarantine review celery enqueue failed media_id=%s", media_id, exc_info=True)
        try:
            from app.database.session import SessionLocal

            with SessionLocal() as db:
                send_quarantine_review_message(db, int(media_id))
        except Exception:
            logger.debug("quarantine review sync fallback failed media_id=%s", media_id, exc_info=True)
