"""Shared quarantine batch review cards — Q&A topic (10+1) and inbox destinations."""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_storage_hub_map import GATEKEEPER_REVIEW_TOPIC_TITLE, STORAGE_HUB_IDENT
from app.services.gatekeeper_review import (
    _bot_token,
    _classification_dict,
    _telegram_api_post,
    gatekeeper_verdict_from_media,
    html_escape,
    resolve_media_lane_key,
    review_chat_id,
    review_thread_id,
)
from app.services.media_gatekeeper import gatekeeper_verdict_from_media

logger = logging.getLogger(__name__)

LANE_PENDING_PREFIX = "tbcc:quarantine:lane:"
BATCH_KEY_PREFIX = "tbcc:quarantine:batch:"
BATCH_LEAD_PREFIX = "tbcc:quarantine:batch_lead:"
BATCH_TTL_SECONDS = 86400 * 7

CALLBACK_BATCH_APPROVE = "gk:ba:"
CALLBACK_BATCH_REJECT = "gk:br:"
CALLBACK_BATCH_TOGGLE = "gk:bt:"

MIN_ALBUM_POST = 2


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def review_batch_size() -> int:
    raw = (os.getenv("TBCC_REVIEW_BATCH_SIZE") or "10").strip()
    try:
        return max(MIN_ALBUM_POST, min(11, int(raw)))
    except ValueError:
        return 10


def lane_pending_key(lane_key: str) -> str:
    return f"{LANE_PENDING_PREFIX}{(lane_key or '').strip().lower()}"


def _store_batch(
    batch_id: str,
    media_ids: list[int],
    *,
    lane_key: str | None = None,
    lead_media_id: int | None = None,
) -> None:
    """Persist batch members + optional Storage Hub lane. Index lead → batch for toggle fan-out."""
    payload = {
        "media_ids": [int(x) for x in media_ids],
        "lane_key": (lane_key or "").strip().lower() or None,
        "lead_media_id": int(lead_media_id) if lead_media_id else (int(media_ids[0]) if media_ids else None),
    }
    try:
        r = _redis()
        r.set(f"{BATCH_KEY_PREFIX}{batch_id}", json.dumps(payload), ex=BATCH_TTL_SECONDS)
        lead = payload.get("lead_media_id")
        if lead:
            r.set(f"{BATCH_LEAD_PREFIX}{int(lead)}", batch_id, ex=BATCH_TTL_SECONDS)
    except Exception:
        logger.debug("quarantine batch store failed id=%s", batch_id, exc_info=True)


def load_batch_payload(batch_id: str) -> dict[str, Any]:
    try:
        raw = _redis().get(f"{BATCH_KEY_PREFIX}{batch_id}")
        if not raw:
            return {}
        data = json.loads(raw)
        if isinstance(data, list):
            # Legacy shape: bare media_id list
            return {"media_ids": [int(x) for x in data], "lane_key": None, "lead_media_id": int(data[0]) if data else None}
        if isinstance(data, dict):
            ids = [int(x) for x in (data.get("media_ids") or [])]
            return {
                "media_ids": ids,
                "lane_key": (data.get("lane_key") or None),
                "lead_media_id": int(data["lead_media_id"]) if data.get("lead_media_id") else (ids[0] if ids else None),
            }
    except Exception:
        logger.debug("quarantine batch load failed id=%s", batch_id, exc_info=True)
    return {}


def load_batch_media_ids(batch_id: str) -> list[int]:
    return list(load_batch_payload(batch_id).get("media_ids") or [])


def batch_id_for_lead_media(lead_media_id: int) -> str | None:
    try:
        raw = _redis().get(f"{BATCH_LEAD_PREFIX}{int(lead_media_id)}")
        return str(raw) if raw else None
    except Exception:
        return None


def fanout_batch_lane_picks(batch_id: str, lanes: list[str]) -> list[int]:
    """Write the same operator lane picks onto every media id in the batch."""
    from app.services.gatekeeper_lane_picker import set_picked_lanes

    ids = load_batch_media_ids(batch_id)
    clean = list(lanes or [])
    for mid in ids:
        set_picked_lanes(int(mid), clean)
    return ids


def toggle_batch_picked_lane(batch_id: str, lane_key: str) -> list[str]:
    """Toggle a lane for the whole batch (UI is one card → one choice for all items)."""
    from app.services.gatekeeper_lane_picker import get_picked_lanes, toggle_picked_lane

    payload = load_batch_payload(batch_id)
    ids = list(payload.get("media_ids") or [])
    if not ids:
        return []
    lead = int(payload.get("lead_media_id") or ids[0])
    selected = toggle_picked_lane(lead, lane_key)
    fanout_batch_lane_picks(batch_id, selected)
    # Re-read lead as source of truth after fan-out
    return get_picked_lanes(lead)

def lane_quarantine_buffer_count(lane_key: str) -> int:
    try:
        return int(_redis().llen(lane_pending_key(lane_key)))
    except Exception:
        return 0


def batch_review_keyboard(batch_id: str, lead_media_id: int, lane_key: str | None = None) -> dict[str, Any]:
    from app.services.gatekeeper_lane_picker import (
        get_picked_lanes,
        lane_button_label,
        gatekeeper_lane_picker_keys,
    )
    from app.services.gatekeeper_review import panel_open_callback

    picked = set(get_picked_lanes(int(lead_media_id)))
    if lane_key and not picked:
        picked = {(lane_key or "").strip().lower()}
    rows: list[list[dict[str, str]]] = []
    row: list[dict[str, str]] = []
    for lane in gatekeeper_lane_picker_keys():
        row.append(
            {
                "text": lane_button_label(lane, selected=lane in picked),
                "callback_data": f"{CALLBACK_BATCH_TOGGLE}{batch_id}:{lane}",
            }
        )
        if len(row) >= 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            {"text": "✅ Approve batch", "callback_data": f"{CALLBACK_BATCH_APPROVE}{batch_id}"},
            {"text": "🗑 Reject batch", "callback_data": f"{CALLBACK_BATCH_REJECT}{batch_id}"},
        ]
    )
    lane_for_open = (lane_key or "").strip().lower() or (sorted(picked)[0] if picked else None)
    rows.append(
        [{"text": "📋 Review all waiting", "callback_data": panel_open_callback(lane_for_open)}]
    )
    return {"inline_keyboard": rows}


def format_batch_caption(
    db: Session,
    media_rows: list[Any],
    *,
    batch_id: str,
    label: str,
    lane_key: str | None = None,
) -> str:
    lines = [
        f"🟡 <b>{html_escape(label)}</b> batch <code>{batch_id}</code> · "
        f"{len(media_rows)} item(s)",
    ]
    if lane_key:
        lines.append(f"Lane: <code>{html_escape(lane_key.upper())}</code>")
    numbered: list[str] = []
    for m in media_rows:
        mid = int(m.id)
        meta = _classification_dict(m).get("gatekeeper") or {}
        score = meta.get("quality_score", "?")
        lane = resolve_media_lane_key(db, m) or lane_key or "?"
        numbered.append(f"{mid:04d} · {html_escape(str(lane).upper())} · {score}")
    lines.append("<code>" + html_escape("\n".join(numbered[:15])) + "</code>")
    if len(numbered) > 15:
        lines.append(f"<i>… +{len(numbered) - 15} more in batch</i>")
    lines.append("<i>Batch = one lane choice for all items. Tap lane emoji(s), then Approve — or Reject entire batch.</i>")
    from app.services.tbcc_caption_stamp import merge_quarantine_review_html

    return merge_quarantine_review_html("\n".join(lines), lane_key=lane_key)


def qa_review_dest() -> dict[str, Any]:
    dest: dict[str, Any] = {"chat_id": review_chat_id()}
    tid = review_thread_id()
    if tid:
        dest["message_thread_id"] = int(tid)
    return dest


def post_quarantine_batch(
    db: Session,
    media_ids: list[int],
    *,
    dest: dict[str, Any],
    label: str,
    lane_key: str | None = None,
) -> dict[str, Any]:
    """Copy previews + post control card (10+1 when batch has 11 items)."""
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

    batch_id = secrets.token_hex(4)
    album_size = review_batch_size()
    album_ids = [int(m.id) for m in quarantine[:album_size]]
    lead_id = int(quarantine[album_size].id) if len(quarantine) > album_size else int(quarantine[0].id)
    _store_batch(
        batch_id,
        [int(m.id) for m in quarantine],
        lane_key=lane_key,
        lead_media_id=lead_id,
    )

    previews: list[dict[str, Any]] = []
    for m in quarantine:
        from app.services.gatekeeper_review import resolve_preview_copy_target

        preview = resolve_preview_copy_target(m)
        if preview:
            previews.append({"media_id": int(m.id), **preview})

    copied_ids: list[int] = []
    for preview in previews:
        if int(preview.get("media_id") or 0) not in album_ids:
            continue
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

    caption = format_batch_caption(
        db,
        quarantine,
        batch_id=batch_id,
        label=label,
        lane_key=lane_key,
    )
    keyboard = batch_review_keyboard(batch_id, lead_id, lane_key=lane_key)

    lead_preview = next((p for p in previews if int(p.get("media_id") or 0) == lead_id), None)
    control_sent = False
    if lead_preview and len(quarantine) > album_size:
        payload: dict[str, Any] = {
            "chat_id": dest["chat_id"],
            "from_chat_id": lead_preview["from_chat_id"],
            "message_id": int(lead_preview["message_id"]),
            "caption": caption,
            "parse_mode": "HTML",
            "reply_markup": keyboard,
        }
        if dest.get("message_thread_id"):
            payload["message_thread_id"] = int(dest["message_thread_id"])
        sent = _telegram_api_post(token, "copyMessage", payload)
        control_sent = bool(sent.get("ok"))
        if not control_sent:
            logger.info("quarantine lead copyMessage failed batch=%s", batch_id)

    if not control_sent:
        control_payload: dict[str, Any] = {
            "chat_id": dest["chat_id"],
            "text": caption,
            "parse_mode": "HTML",
            "reply_markup": keyboard,
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
            gk["quarantine_review_posted"] = True
            gk["quarantine_review_batch"] = batch_id
            gk["quarantine_review_at"] = time.time()
            if lane_key:
                gk["quarantine_review_lane"] = lane_key
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
        "lane_key": lane_key,
    }


def queue_lane_quarantine_media(media_id: int, lane_key: str) -> dict[str, Any]:
    """Buffer quarantined lane media; flush Q&A batch when buffer reaches review_batch_size."""
    key = (lane_key or "").strip().lower()
    if not key:
        return {"queued": False, "reason": "no_lane_key"}
    mid = int(media_id)
    album_size = review_batch_size()
    pending_key = lane_pending_key(key)
    try:
        r = _redis()
        existing = {int(x) for x in (r.lrange(pending_key, 0, -1) or []) if str(x).isdigit()}
        if mid in existing:
            return {"queued": True, "duplicate": True, "lane_key": key}
        r.rpush(pending_key, str(mid))
        pending = int(r.llen(pending_key))
        if pending >= album_size:
            take = album_size + 1 if pending > album_size else album_size
            ids = [int(x) for x in (r.lrange(pending_key, 0, take - 1) or [])]
            r.ltrim(pending_key, take, -1)
            return {
                "queued": True,
                "flushing": True,
                "lane_key": key,
                "media_ids": ids,
                "pending_left": pending - take,
            }
        return {"queued": True, "flushing": False, "lane_key": key, "pending": pending, "album_size": album_size}
    except Exception as e:
        logger.warning("lane quarantine queue failed lane=%s media=%s: %s", key, mid, e)
        return {"queued": False, "error": str(e)[:200]}


def flush_lane_quarantine_buffer(db: Session, lane_key: str, *, force: bool = False) -> dict[str, Any]:
    key = (lane_key or "").strip().lower()
    if not key:
        return {"ok": False, "reason": "no_lane_key"}
    album_size = review_batch_size()
    try:
        r = _redis()
        pending = int(r.llen(lane_pending_key(key)))
        if pending < 1:
            return {"ok": True, "skipped": True, "reason": "empty"}
        if not force and pending < album_size:
            return {"ok": True, "skipped": True, "reason": "below_album_size", "pending": pending}
        take = album_size + 1 if pending > album_size else min(pending, album_size)
        if force and pending < album_size:
            take = min(pending, album_size + 1)
        ids = [int(x) for x in (r.lrange(lane_pending_key(key), 0, take - 1) or [])]
        r.ltrim(lane_pending_key(key), take, -1)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}

    label = GATEKEEPER_REVIEW_TOPIC_TITLE or "Q&A REVIEW"
    return post_quarantine_batch(
        db,
        ids,
        dest=qa_review_dest(),
        label=label,
        lane_key=key,
    )


def post_lane_quarantine_batch(db: Session, lane_key: str, media_ids: list[int]) -> dict[str, Any]:
    label = GATEKEEPER_REVIEW_TOPIC_TITLE or "Q&A REVIEW"
    return post_quarantine_batch(
        db,
        media_ids,
        dest=qa_review_dest(),
        label=label,
        lane_key=(lane_key or "").strip().lower() or None,
    )


def parse_batch_review_callback(data: str | None) -> tuple[str, str] | tuple[str, str, str] | None:
    raw = (data or "").strip()
    if raw.startswith(CALLBACK_BATCH_TOGGLE):
        rest = raw[len(CALLBACK_BATCH_TOGGLE) :]
        if ":" not in rest:
            return None
        batch_id, lane = rest.split(":", 1)
        return ("toggle_lane", batch_id, lane)
    if raw.startswith(CALLBACK_BATCH_APPROVE):
        return ("approve", raw[len(CALLBACK_BATCH_APPROVE) :])
    if raw.startswith(CALLBACK_BATCH_REJECT):
        return ("reject", raw[len(CALLBACK_BATCH_REJECT) :])
    return None


def _lanes_for_batch_item(
    db: Session,
    media_id: int,
    *,
    batch_lane_key: str | None,
    operator_picks: list[str] | None,
) -> list[str] | None:
    """Resolve lanes for one batch member without stamping lead-only Redis onto siblings.

    Priority:
    1. Explicit operator picks (fan-out already wrote the same list on every id)
    2. Batch's Storage Hub lane_key (whole batch came from one lane buffer)
    3. Per-item resolve_media_lane_key / storage expected lane
    """
    from app.models.media import Media

    if operator_picks:
        return list(operator_picks)
    if batch_lane_key:
        return [batch_lane_key]
    media = db.query(Media).filter(Media.id == int(media_id)).first()
    if not media:
        return None
    fallback = resolve_media_lane_key(db, media)
    if fallback and fallback not in ("inbox", "packs"):
        return [fallback]
    return None


def operator_approve_batch(db: Session, batch_id: str, *, operator_id: int | None = None) -> dict[str, Any]:
    from app.services.gatekeeper_lane_picker import get_picked_lanes
    from app.services.gatekeeper_review import operator_approve_media

    payload = load_batch_payload(batch_id)
    ids = list(payload.get("media_ids") or [])
    if not ids:
        return {"ok": False, "reason": "batch_not_found", "batch_id": batch_id}

    batch_lane = (payload.get("lane_key") or "").strip().lower() or None
    lead_id = int(payload.get("lead_media_id") or ids[0])
    # Operator toggles fan out to every id; any member's picks reflect the batch choice.
    operator_picks = get_picked_lanes(lead_id) or get_picked_lanes(int(ids[0]))
    if operator_picks:
        fanout_batch_lane_picks(batch_id, operator_picks)

    results = []
    for mid in ids:
        lanes = _lanes_for_batch_item(
            db,
            int(mid),
            batch_lane_key=batch_lane,
            operator_picks=operator_picks or None,
        )
        results.append(
            operator_approve_media(db, int(mid), operator_id=operator_id, lane_keys=lanes)
        )
    ok = sum(1 for r in results if r.get("ok"))
    route_fail = sum(1 for r in results if r.get("ok") and r.get("route_enqueue_ok") is False)
    return {
        "ok": ok > 0,
        "batch_id": batch_id,
        "approved": ok,
        "total": len(ids),
        "route_enqueue_failures": route_fail,
        "results": results,
    }


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


def is_storage_lane_source(media: Any) -> bool:
    """True when media originated from a mapped Storage Hub content lane topic."""
    from app.data.aof_storage_hub_map import CONTENT_LANE_NETWORK_KEYS, STORAGE_HUB_IDENT
    from app.services.media_gatekeeper import expected_lane_for_storage_source

    lane = expected_lane_for_storage_source(getattr(media, "source_channel", None))
    if not lane or lane not in CONTENT_LANE_NETWORK_KEYS or lane in ("inbox", "packs"):
        return False
    src = (getattr(media, "source_channel", None) or "").strip()
    hub = STORAGE_HUB_IDENT.lstrip("-")
    return hub in src.replace("telegram:", "")
