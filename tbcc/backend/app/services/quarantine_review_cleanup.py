"""Delete Q&A quarantine review Telegram messages after operator decide."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def quarantine_review_cleanup_enabled() -> bool:
    return (os.getenv("TBCC_QUARANTINE_REVIEW_CLEANUP") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _delete_messages_http(chat_id: int, message_ids: list[int]) -> dict[str, Any]:
    from app.services.gatekeeper_review import _bot_token, _telegram_api_post

    token = _bot_token()
    if not token:
        return {"ok": False, "reason": "bot_token_unset"}
    deleted = 0
    errors: list[str] = []
    seen: set[int] = set()
    for mid in message_ids:
        imid = int(mid)
        if imid <= 0 or imid in seen:
            continue
        seen.add(imid)
        out = _telegram_api_post(
            token,
            "deleteMessage",
            {"chat_id": int(chat_id), "message_id": imid},
        )
        if out.get("ok"):
            deleted += 1
        else:
            errors.append(str(out.get("error") or "delete_failed")[:120])
    return {"ok": deleted > 0 or not seen, "deleted": deleted, "errors": errors}


def _clear_media_review_messages(media: Any) -> tuple[list[int], int | None]:
    data = {}
    raw = getattr(media, "classification_json", None)
    if raw:
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
    gk = data.get("gatekeeper") if isinstance(data.get("gatekeeper"), dict) else {}
    chat_id = gk.pop("quarantine_review_chat_id", None)
    ids = list(gk.pop("quarantine_review_message_ids", None) or [])
    if gk:
        data["gatekeeper"] = gk
    else:
        data.pop("gatekeeper", None)
    media.classification_json = json.dumps(data, ensure_ascii=False) if data else None
    return [int(x) for x in ids if int(x) > 0], int(chat_id) if chat_id else None


def cleanup_media_quarantine_messages(db: Session, media_id: int) -> dict[str, Any]:
    """Best-effort delete Telegram review card(s) for one media row."""
    if not quarantine_review_cleanup_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}
    from app.models.media import Media
    from app.services.gatekeeper_review import review_chat_id

    media = db.query(Media).filter(Media.id == int(media_id)).first()
    if not media:
        return {"ok": False, "reason": "not_found"}
    ids, chat_id = _clear_media_review_messages(media)
    db.commit()
    if not ids:
        return {"ok": True, "skipped": True, "reason": "no_messages", "media_id": int(media_id)}
    cid = int(chat_id or review_chat_id())
    out = _delete_messages_http(cid, ids)
    out["media_id"] = int(media_id)
    return out


def cleanup_batch_quarantine_messages(batch_id: str) -> dict[str, Any]:
    """Delete preview copies + control card for a quarantine batch."""
    if not quarantine_review_cleanup_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}
    from app.services.gatekeeper_review import review_chat_id
    from app.services.quarantine_batch_review import load_batch_payload, save_batch_telegram_meta

    payload = load_batch_payload(batch_id)
    tel = payload.get("telegram") if isinstance(payload.get("telegram"), dict) else {}
    chat_id = int(tel.get("chat_id") or review_chat_id())
    preview_ids = [int(x) for x in (tel.get("preview_message_ids") or []) if int(x) > 0]
    control_id = int(tel.get("control_message_id") or 0)
    message_ids = preview_ids + ([control_id] if control_id > 0 else [])
    save_batch_telegram_meta(batch_id, chat_id=chat_id, preview_message_ids=[], control_message_id=0)
    if not message_ids:
        return {"ok": True, "skipped": True, "reason": "no_messages", "batch_id": batch_id}
    out = _delete_messages_http(chat_id, message_ids)
    out["batch_id"] = batch_id
    return out


def cleanup_media_ids_quarantine_messages(db: Session, media_ids: list[int]) -> dict[str, Any]:
    deleted = 0
    for mid in media_ids:
        out = cleanup_media_quarantine_messages(db, int(mid))
        deleted += int(out.get("deleted") or 0)
    return {"ok": True, "deleted": deleted, "media_ids": media_ids}
