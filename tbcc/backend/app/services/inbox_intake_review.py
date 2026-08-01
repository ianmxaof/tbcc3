"""Inbox intake — quarantine album cards posted inside inbox topic/channel."""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_storage_hub_map import (
    INBOX_CHANNEL_IDENT,
    INBOX_TOPIC_ID,
    STORAGE_HUB_IDENT,
)
from app.services.gatekeeper_review import _bot_token, _telegram_api_post, html_escape
from app.services.intake_scheduler import get_album_size
from app.services.media_gatekeeper import gatekeeper_verdict_from_media

logger = logging.getLogger(__name__)

PENDING_KEY = "tbcc:inbox:quarantine:pending"
BATCH_KEY_PREFIX = "tbcc:inbox:batch:"
BATCH_TTL_SECONDS = 86400 * 7

CALLBACK_BATCH_APPROVE = "gk:ba:"
CALLBACK_BATCH_REJECT = "gk:br:"


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def inbox_intake_enabled() -> bool:
    return (os.getenv("TBCC_INBOX_INTAKE_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def is_inbox_source_label(source_channel: str | None) -> bool:
    raw = (source_channel or "").strip().lower()
    if not raw:
        return False
    if f"#topic:{INBOX_TOPIC_ID}" in raw:
        return True
    ch = INBOX_CHANNEL_IDENT.lstrip("-")
    return INBOX_CHANNEL_IDENT in raw or ch in raw.replace("telegram:", "")


def is_inbox_media(media: Any) -> bool:
    return is_inbox_source_label(getattr(media, "source_channel", None))


def _review_dest_for_media(media: Any) -> dict[str, Any]:
    """Post review cards back into the inbox subtopic or shortcut channel."""
    src = (getattr(media, "source_channel", None) or "").strip()
    if INBOX_CHANNEL_IDENT.lstrip("-") in src.replace("telegram:", ""):
        return {"chat_id": int(INBOX_CHANNEL_IDENT), "message_thread_id": None}
    return {"chat_id": int(STORAGE_HUB_IDENT), "message_thread_id": int(INBOX_TOPIC_ID)}


def queue_inbox_quarantine_media(media_id: int) -> dict[str, Any]:
    """Buffer quarantined inbox media; flush album when batch is full."""
    if not inbox_intake_enabled():
        return {"queued": False, "reason": "disabled"}
    mid = int(media_id)
    try:
        r = _redis()
        r.rpush(PENDING_KEY, str(mid))
        pending = int(r.llen(PENDING_KEY))
        album_size = get_album_size()
        if pending >= album_size:
            ids = [int(x) for x in (r.lrange(PENDING_KEY, 0, album_size - 1) or [])]
            r.ltrim(PENDING_KEY, album_size, -1)
            return {"queued": True, "flushing": True, "media_ids": ids, "pending_left": pending - album_size}
        return {"queued": True, "flushing": False, "pending": pending, "album_size": album_size}
    except Exception as e:
        logger.warning("inbox quarantine queue failed media_id=%s: %s", mid, e)
        return {"queued": False, "error": str(e)[:200]}


def flush_pending_inbox_quarantine(*, force: bool = False) -> dict[str, Any]:
    """Post any buffered inbox quarantine items as one album card."""
    if not inbox_intake_enabled():
        return {"ok": False, "reason": "disabled"}
    try:
        r = _redis()
        pending = int(r.llen(PENDING_KEY))
        if pending < 1:
            return {"ok": True, "skipped": True, "reason": "empty"}
        album_size = get_album_size()
        if not force and pending < album_size:
            return {"ok": True, "skipped": True, "reason": "below_album_size", "pending": pending}
        take = min(pending, album_size) if not force else min(pending, album_size)
        if force and pending > 0:
            take = min(pending, album_size)
        ids = [int(x) for x in (r.lrange(PENDING_KEY, 0, take - 1) or [])]
        r.ltrim(PENDING_KEY, take, -1)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}

    from app.database.session import SessionLocal

    with SessionLocal() as db:
        out = post_inbox_quarantine_batch(db, ids)
    return out


def _store_batch(batch_id: str, media_ids: list[int]) -> None:
    try:
        _redis().set(
            f"{BATCH_KEY_PREFIX}{batch_id}",
            json.dumps([int(x) for x in media_ids]),
            ex=BATCH_TTL_SECONDS,
        )
    except Exception:
        logger.debug("inbox batch store failed id=%s", batch_id, exc_info=True)


def load_batch_media_ids(batch_id: str) -> list[int]:
    try:
        raw = _redis().get(f"{BATCH_KEY_PREFIX}{batch_id}")
        if not raw:
            return []
        data = json.loads(raw)
        if isinstance(data, list):
            return [int(x) for x in data]
    except Exception:
        logger.debug("inbox batch load failed id=%s", batch_id, exc_info=True)
    return []


def batch_review_keyboard(batch_id: str, lead_media_id: int) -> dict[str, Any]:
    from app.services.gatekeeper_lane_picker import review_lane_picker_keyboard

    kb = review_lane_picker_keyboard(int(lead_media_id))
    rows = []
    for row in kb.get("inline_keyboard") or []:
        new_row = []
        for btn in row:
            data = str(btn.get("callback_data") or "")
            text = str(btn.get("text") or "")
            if data.startswith("gk:a:"):
                new_row.append({"text": text, "callback_data": f"{CALLBACK_BATCH_APPROVE}{batch_id}"})
            elif data.startswith("gk:r:"):
                new_row.append({"text": text, "callback_data": f"{CALLBACK_BATCH_REJECT}{batch_id}"})
            else:
                new_row.append(btn)
        rows.append(new_row)
    return {"inline_keyboard": rows}


def post_inbox_quarantine_batch(db: Session, media_ids: list[int]) -> dict[str, Any]:
    """Copy inbox media previews + post one control card with batch approve/reject."""
    from app.models.media import Media

    ids = [int(x) for x in media_ids if int(x) > 0]
    if not ids:
        return {"ok": False, "reason": "empty"}

    rows = db.query(Media).filter(Media.id.in_(ids)).all()
    by_id = {int(m.id): m for m in rows}
    ordered = [by_id[mid] for mid in ids if mid in by_id]
    if not ordered:
        return {"ok": False, "reason": "not_found"}

    quarantine = [m for m in ordered if gatekeeper_verdict_from_media(m) == "quarantine"]
    if not quarantine:
        return {"ok": False, "reason": "not_quarantine", "media_ids": ids}

    token = _bot_token()
    if not token:
        return {"ok": False, "reason": "bot_token_unset"}

    dest = _review_dest_for_media(quarantine[0])
    batch_id = secrets.token_hex(4)
    _store_batch(batch_id, [int(m.id) for m in quarantine])

    previews: list[dict[str, Any]] = []
    for m in quarantine:
        from app.services.gatekeeper_review import resolve_preview_copy_target

        preview = resolve_preview_copy_target(m)
        if preview:
            previews.append(preview)

    copied_ids: list[int] = []
    for preview in previews[:10]:
        payload: dict[str, Any] = {
            "chat_id": dest["chat_id"],
            "from_chat_id": preview["from_chat_id"],
            "message_id": int(preview["message_id"]),
        }
        if dest.get("message_thread_id"):
            payload["message_thread_id"] = int(dest["message_thread_id"])
        out = _telegram_api_post(token, "copyMessage", payload)
        if out.get("ok"):
            mid = (out.get("result") or {}).get("message_id")
            if mid:
                copied_ids.append(int(mid))

    scores = []
    for m in quarantine:
        try:
            meta = json.loads(m.classification_json or "{}")
            scores.append(meta.get("gatekeeper", {}).get("quality_score", "?"))
        except Exception:
            scores.append("?")

    caption = (
        f"🟡 <b>INBOX QUARANTINE</b> batch <code>{batch_id}</code> · "
        f"{len(quarantine)} item(s)\n"
        f"Scores: <code>{html_escape(', '.join(str(s) for s in scores[:10]))}</code>\n"
        f"<i>Tap lane emoji(s), then Approve — or Reject entire album.</i>"
    )
    control_payload: dict[str, Any] = {
        "chat_id": dest["chat_id"],
        "text": caption,
        "parse_mode": "HTML",
        "reply_markup": batch_review_keyboard(batch_id, int(quarantine[0].id)),
        "disable_web_page_preview": True,
    }
    if dest.get("message_thread_id"):
        control_payload["message_thread_id"] = int(dest["message_thread_id"])
    if copied_ids:
        control_payload["reply_to_message_id"] = copied_ids[0]

    sent = _telegram_api_post(token, "sendMessage", control_payload)
    if not sent.get("ok"):
        return {"ok": False, "error": sent.get("error"), "batch_id": batch_id, "media_ids": ids}

    for m in quarantine:
        try:
            meta = json.loads(m.classification_json or "{}") if m.classification_json else {}
            gk = meta.get("gatekeeper") if isinstance(meta.get("gatekeeper"), dict) else {}
            gk = dict(gk)
            gk["inbox_review_posted"] = True
            gk["inbox_review_batch"] = batch_id
            gk["inbox_review_at"] = time.time()
            meta["gatekeeper"] = gk
            m.classification_json = json.dumps(meta, ensure_ascii=False)
        except Exception:
            pass
    db.commit()

    return {
        "ok": True,
        "batch_id": batch_id,
        "media_ids": [int(m.id) for m in quarantine],
        "copied_preview_ids": copied_ids,
        "dest": dest,
    }


def parse_batch_review_callback(data: str | None) -> tuple[str, str] | None:
    raw = (data or "").strip()
    if raw.startswith(CALLBACK_BATCH_APPROVE):
        return ("approve", raw[len(CALLBACK_BATCH_APPROVE) :])
    if raw.startswith(CALLBACK_BATCH_REJECT):
        return ("reject", raw[len(CALLBACK_BATCH_REJECT) :])
    return None


def operator_approve_batch(db: Session, batch_id: str, *, operator_id: int | None = None) -> dict[str, Any]:
    from app.services.gatekeeper_lane_picker import get_picked_lanes
    from app.services.gatekeeper_review import operator_approve_media

    ids = load_batch_media_ids(batch_id)
    if not ids:
        return {"ok": False, "reason": "batch_not_found", "batch_id": batch_id}
    lane_keys = get_picked_lanes(int(ids[0]))
    results = []
    for mid in ids:
        results.append(
            operator_approve_media(db, mid, operator_id=operator_id, lane_keys=lane_keys or None)
        )
    ok = sum(1 for r in results if r.get("ok"))
    return {"ok": ok > 0, "batch_id": batch_id, "approved": ok, "total": len(ids), "results": results}


def operator_reject_batch(db: Session, batch_id: str, *, operator_id: int | None = None) -> dict[str, Any]:
    from app.services.gatekeeper_review import operator_reject_media

    ids = load_batch_media_ids(batch_id)
    if not ids:
        return {"ok": False, "reason": "batch_not_found", "batch_id": batch_id}
    results = []
    for mid in ids:
        results.append(operator_reject_media(db, mid, operator_id=operator_id))
    ok = sum(1 for r in results if r.get("ok"))
    return {"ok": ok > 0, "batch_id": batch_id, "rejected": ok, "total": len(ids), "results": results}
