"""Operator quarantine review — Telegram notify + approve/reject actions."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT
from app.services.storage_hub_bot_wiring import gatekeeper_review_bot_default
from app.services.gatekeeper_source_demote import record_operator_approve, record_operator_reject
from app.services.media_gatekeeper import (
    gatekeeper_verdict_from_media,
    parse_source_channel_id,
)
from app.services.scrape_channel_intel import pool_key_for_pool_id

logger = logging.getLogger(__name__)

CALLBACK_APPROVE = "gk:a:"
CALLBACK_REJECT = "gk:r:"
CALLBACK_PANEL_APPROVE = "gk:p:approve"
CALLBACK_PANEL_APPROVE_CONFIRM = "gk:p:approve:yes"
CALLBACK_PANEL_REFRESH = "gk:p:refresh"
CALLBACK_PANEL_CANCEL = "gk:p:cancel"
CALLBACK_PANEL_OPEN = "gk:p:open"


def panel_open_callback(lane_key: str | None = None) -> str:
    lane = _normalize_panel_lane_key(lane_key)
    return f"{CALLBACK_PANEL_OPEN}:{lane}" if lane else CALLBACK_PANEL_OPEN


def panel_refresh_callback(lane_key: str | None = None) -> str:
    lane = _normalize_panel_lane_key(lane_key)
    return f"{CALLBACK_PANEL_REFRESH}:{lane}" if lane else CALLBACK_PANEL_REFRESH


def panel_approve_callback(lane_key: str | None = None) -> str:
    lane = _normalize_panel_lane_key(lane_key)
    return f"{CALLBACK_PANEL_APPROVE}:{lane}" if lane else CALLBACK_PANEL_APPROVE


def panel_approve_confirm_callback(lane_key: str | None = None) -> str:
    lane = _normalize_panel_lane_key(lane_key)
    return f"{CALLBACK_PANEL_APPROVE_CONFIRM}:{lane}" if lane else CALLBACK_PANEL_APPROVE_CONFIRM


def panel_cancel_callback(lane_key: str | None = None) -> str:
    lane = _normalize_panel_lane_key(lane_key)
    return f"{CALLBACK_PANEL_CANCEL}:{lane}" if lane else CALLBACK_PANEL_CANCEL


def parse_panel_callback(data: str | None) -> tuple[str, str | None] | None:
    """Parse gk:p:* panel callbacks → (action, lane_key)."""
    raw = (data or "").strip()
    if not raw.startswith("gk:p:"):
        return None
    rest = raw[len("gk:p:"):]
    if rest == "open":
        return ("open", None)
    if rest.startswith("open:"):
        return ("open", _normalize_panel_lane_key(rest[5:]))
    if rest == "refresh":
        return ("refresh", None)
    if rest.startswith("refresh:"):
        return ("refresh", _normalize_panel_lane_key(rest[8:]))
    if rest == "cancel":
        return ("cancel", None)
    if rest.startswith("cancel:"):
        return ("cancel", _normalize_panel_lane_key(rest[7:]))
    if rest == "approve":
        return ("approve", None)
    if rest.startswith("approve:yes"):
        suffix = rest[len("approve:yes"):].lstrip(":")
        return ("approve_yes", _normalize_panel_lane_key(suffix) if suffix else None)
    if rest.startswith("approve:"):
        return ("approve", _normalize_panel_lane_key(rest[8:]))
    return None

_QUARANTINE_JSON_MARKERS = ('"verdict": "quarantine"', '"verdict":"quarantine"')

_TOPIC_SOURCE_RE = re.compile(
    r"telegram:(?P<chat>-?\d+)#topic:(?P<thread>\d+)",
    re.IGNORECASE,
)


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
    if raw:
        try:
            return int(raw)
        except ValueError:
            return None
    from app.data.aof_storage_hub_map import GATEKEEPER_REVIEW_TOPIC_ID

    return GATEKEEPER_REVIEW_TOPIC_ID


def _bot_token() -> str:
    """
    Bot that posts review cards must also handle gk:a/gk:r callbacks.
    Default follows storage hub owner (album composer / remixer when payment hub is off).
    """
    which = gatekeeper_review_bot_default()
    if which in ("album", "album_composer", "composer", "ac"):
        return (
            os.getenv("TBCC_ALBUM_COMPOSER_BOT_TOKEN")
            or os.getenv("BOT_TOKEN")
            or os.getenv("TBCC_PAYMENT_BOT_TOKEN")
            or ""
        ).strip()
    return (
        os.getenv("TBCC_PAYMENT_BOT_TOKEN")
        or os.getenv("BOT_TOKEN")
        or os.getenv("TBCC_ALBUM_COMPOSER_BOT_TOKEN")
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
    from app.services.tbcc_caption_stamp import merge_quarantine_review_html

    body = (
        f"🟡 <b>QUARANTINE</b> #{media.id} · {lane} · quality <b>{score}</b>/100\n"
        f"<code>{mt}</code> · <code>{html_escape(src)}</code>\n"
        f"<i>{html_escape(flag_line)}</i>\n"
        f"<i>Quality score (not ML confidence): ≥70 may auto-approve on trusted hub ingest; "
        f"40–69 = your call.</i>"
    )
    lane_key = str(expected or lane or "").strip().lower() or None
    if lane_key == "?":
        lane_key = None
    return merge_quarantine_review_html(body, lane_key=lane_key)


def html_escape(text: str) -> str:
    import html

    return html.escape(str(text or ""), quote=False)


def review_inline_keyboard(media_id: int, *, default_lane_key: str | None = None) -> dict[str, Any]:
    from app.services.gatekeeper_lane_picker import lane_picker_enabled, review_lane_picker_keyboard

    if lane_picker_enabled():
        return review_lane_picker_keyboard(media_id, default_lane_key=default_lane_key)
    mid = int(media_id)
    open_cb = panel_open_callback(default_lane_key)
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Approve", "callback_data": f"{CALLBACK_APPROVE}{mid}"},
                {"text": "🗑 Reject", "callback_data": f"{CALLBACK_REJECT}{mid}"},
            ],
            [{"text": "📋 Review all waiting", "callback_data": open_cb}],
        ]
    }


def parse_review_callback(data: str | None) -> tuple[str, int] | None:
    raw = (data or "").strip()
    if raw.startswith(CALLBACK_APPROVE):
        return ("approve", int(raw[len(CALLBACK_APPROVE) :]))
    if raw.startswith(CALLBACK_REJECT):
        return ("reject", int(raw[len(CALLBACK_REJECT) :]))
    from app.services.gatekeeper_lane_picker import CALLBACK_TOGGLE

    if raw.startswith(CALLBACK_TOGGLE):
        rest = raw[len(CALLBACK_TOGGLE) :]
        if ":" not in rest:
            return None
        mid_s, lane = rest.split(":", 1)
        return ("toggle_lane", int(mid_s), lane.strip().lower())
    return None


def approve_triggers_micro_pull() -> bool:
    return (os.getenv("TBCC_GATEKEEPER_APPROVE_MICRO_PULL") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def enqueue_micro_pull_for_lane(lane_key: str) -> None:
    """Queue one SCRP micro-pull into the lane Storage Hub topic (non-blocking)."""
    key = (lane_key or "").strip().lower()
    if not key:
        return
    try:
        from app.workers.scrape_micro_pull_worker import run_lane_micro_pull_task

        run_lane_micro_pull_task.delay(key)
    except Exception:
        logger.debug("approve micro-pull enqueue failed lane=%s", key, exc_info=True)


def resolve_media_lane_key(db: Session, media: Any) -> str | None:
    from app.services.media_gatekeeper import expected_lane_for_storage_source

    lane = expected_lane_for_storage_source(getattr(media, "source_channel", None))
    if lane:
        return lane
    if getattr(media, "pool_id", None):
        lane_key, _ = pool_key_for_pool_id(db, int(media.pool_id))
        return lane_key
    meta = _classification_dict(media).get("gatekeeper") or {}
    expected = (meta.get("globs") or {}).get("lane_fit", {}).get("expected")
    return str(expected).strip().lower() if expected else None


def enqueue_lane_route_for_media(media_id: int, lane_keys: list[str]) -> None:
    if not lane_keys:
        return
    try:
        from app.workers.gatekeeper_review_worker import route_approved_lanes_task

        route_approved_lanes_task.delay(int(media_id), list(lane_keys))
    except Exception:
        logger.debug("lane route enqueue failed media_id=%s", media_id, exc_info=True)


def maybe_vault_and_evict_approved_media(db: Session, media_id: int) -> dict[str, Any]:
    """After operator approve — move to SENT VAULT and evict from work lane."""
    from app.models.media import Media
    from app.services.storage_sent_cache import (
        move_deposit_batch_to_sent_cache,
        storage_sent_cache_enabled,
    )

    if not storage_sent_cache_enabled():
        return {"skipped": True, "reason": "sent_cache_disabled"}
    media = db.query(Media).filter(Media.id == int(media_id)).first()
    if not media or (media.status or "").lower() != "approved":
        return {"skipped": True, "reason": "not_approved"}
    msg_id = int(getattr(media, "telegram_message_id", 0) or 0)
    if msg_id <= 0:
        return {"skipped": True, "reason": "no_telegram_message_id"}
    lane = resolve_media_lane_key(db, media)
    if not lane or lane in ("inbox", "packs"):
        return {"skipped": True, "reason": "no_lane"}
    try:
        from app.services.telegram_admin import run_telegram_import_io
        from app.services.telegram_storage import TelegramStorage

        async def _vault(storage: TelegramStorage):
            return await move_deposit_batch_to_sent_cache(
                storage,
                db,
                stored_messages=[{"message_id": msg_id, "media_id": int(media.id)}],
                network_key=lane,
                hub_ident=STORAGE_HUB_IDENT,
                force_flush=True,
            )

        import asyncio

        return asyncio.run(run_telegram_import_io(_vault))
    except Exception as e:
        logger.warning("vault approved media failed media_id=%s: %s", media_id, e, exc_info=True)
        return {"ok": False, "error": str(e)[:200]}


def enqueue_vault_approved_media(media_id: int) -> None:
    try:
        from app.workers.gatekeeper_review_worker import vault_approved_media_task

        vault_approved_media_task.delay(int(media_id))
    except Exception:
        logger.debug("vault approved enqueue failed media_id=%s", media_id, exc_info=True)


def operator_approve_media(
    db: Session,
    media_id: int,
    *,
    operator_id: int | None = None,
    lane_keys: list[str] | None = None,
) -> dict[str, Any]:
    from app.models.media import Media
    from app.services.export_flywheel_service import pool_id_for_network_key
    from app.services.gatekeeper_lane_picker import (
        clear_picked_lanes,
        get_picked_lanes,
        lane_picker_enabled,
    )

    media = db.query(Media).filter(Media.id == int(media_id)).first()
    if not media:
        return {"ok": False, "reason": "not_found", "media_id": media_id}
    prior = gatekeeper_verdict_from_media(media)
    if prior not in ("quarantine", None) and (media.status or "").lower() == "approved":
        return {"ok": False, "reason": "already_approved", "media_id": media_id}

    selected = sorted({(x or "").strip().lower() for x in (lane_keys or []) if (x or "").strip()})
    if not selected and lane_picker_enabled():
        selected = get_picked_lanes(media_id)
    if not selected:
        fallback = resolve_media_lane_key(db, media)
        if fallback and fallback not in ("inbox", "packs"):
            selected = [fallback]

    media.status = "approved"
    extra: dict[str, Any] = {}
    if selected:
        extra["operator_lanes"] = selected
        extra["lane_stamps"] = selected
        pid = pool_id_for_network_key(db, selected[0])
        if pid:
            media.pool_id = int(pid)
    _merge_operator_action(media, action="approve", operator_id=operator_id, extra=extra or None)
    db.commit()
    record_operator_approve(db, media)
    clear_picked_lanes(media_id)

    routed_lanes: list[str] = []
    if selected and lane_picker_enabled():
        enqueue_lane_route_for_media(media_id, selected)
        routed_lanes = selected

    micro_pull_lanes: list[str] = []
    if approve_triggers_micro_pull():
        for lane in selected or [resolve_media_lane_key(db, media)]:
            if lane:
                enqueue_micro_pull_for_lane(lane)
                micro_pull_lanes.append(lane)
    logger.info(
        "gatekeeper operator approve media_id=%s operator=%s lanes=%s micro_pull=%s",
        media_id,
        operator_id,
        selected,
        micro_pull_lanes,
    )
    enqueue_vault_approved_media(media_id)
    return {
        "ok": True,
        "media_id": media_id,
        "status": "approved",
        "operator_lanes": selected,
        "routed_lanes": routed_lanes,
        "micro_pull_lanes": micro_pull_lanes,
        "micro_pull_lane": micro_pull_lanes[0] if micro_pull_lanes else None,
    }


def bulk_approve_max() -> int:
    raw = (os.getenv("TBCC_GATEKEEPER_BULK_APPROVE_MAX") or "200").strip()
    try:
        return max(1, min(500, int(raw)))
    except ValueError:
        return 200


def _normalize_panel_lane_key(lane_key: str | None) -> str | None:
    from app.data.aof_storage_hub_map import CONTENT_LANE_NETWORK_KEYS

    key = (lane_key or "").strip().lower()
    if not key or key not in CONTENT_LANE_NETWORK_KEYS:
        return None
    return key


def _lane_quarantine_filter(db: Session, lane_key: str):
    from sqlalchemy import or_

    from app.data.aof_storage_hub_map import storage_map_by_key
    from app.models.media import Media
    from app.services.export_flywheel_service import pool_id_for_network_key

    clauses: list[Any] = []
    row = storage_map_by_key().get(lane_key)
    if row:
        clauses.append(Media.source_channel.like(f"%#topic:{int(row.message_thread_id)}%"))
    pid = pool_id_for_network_key(db, lane_key)
    if pid:
        clauses.append(Media.pool_id == int(pid))
    clauses.append(Media.classification_json.like(f'%\"expected\": \"{lane_key}\"%'))
    clauses.append(Media.classification_json.like(f'%\"expected\":\"{lane_key}\"%'))
    if not clauses:
        return None
    return or_(*clauses)


def _quarantine_pending_query(db: Session, lane_key: str | None = None):
    from sqlalchemy import or_

    from app.models.media import Media

    clauses = [Media.classification_json.like(f"%{marker}%") for marker in _QUARANTINE_JSON_MARKERS]
    q = db.query(Media).filter(Media.status == "pending").filter(or_(*clauses))
    lane = _normalize_panel_lane_key(lane_key)
    if lane:
        lane_filter = _lane_quarantine_filter(db, lane)
        if lane_filter is not None:
            q = q.filter(lane_filter)
    return q


def count_quarantine_waiting(db: Session, lane_key: str | None = None) -> int:
    return int(_quarantine_pending_query(db, lane_key=lane_key).count())


def list_quarantine_waiting_ids(
    db: Session,
    *,
    limit: int | None = None,
    lane_key: str | None = None,
) -> list[int]:
    from app.models.media import Media

    cap = int(limit) if limit is not None else bulk_approve_max()
    rows = (
        _quarantine_pending_query(db, lane_key=lane_key)
        .order_by(Media.id.asc())
        .limit(max(1, cap))
        .all()
    )
    return [int(m.id) for m in rows]


def inbox_quarantine_buffer_count() -> int:
    try:
        from app.services.inbox_intake_review import PENDING_KEY, _redis

        return int(_redis().llen(PENDING_KEY))
    except Exception:
        return 0


def format_lane_pool_depth_html(db: Session, *, max_lanes: int = 14) -> str:
    """
    Per-lane approved pool counts for Q&A topic 1 — same depth signal as revenue brief /
    export flywheel backlog pressure (🟠 = depth ≥ 2× policy min).
    """
    from app.services.export_flywheel_service import flywheel_mode, pool_depth_by_lane

    rows = pool_depth_by_lane(db)
    stocked = [r for r in rows if int(r.get("approved_depth") or 0) > 0]
    if not stocked:
        return "Pool approved: <i>none</i>"

    chunks: list[str] = []
    for row in stocked[: max(1, int(max_lanes))]:
        nk = html_escape(str(row.get("network_key") or "?"))
        depth = int(row.get("approved_depth") or 0)
        suffix = "🟠" if row.get("backlog_pressure") else ""
        chunks.append(f"{nk} <b>{depth}</b>{suffix}")

    mode = html_escape(flywheel_mode())
    return (
        f"Pool approved (flywheel <code>{mode}</code>, 🟠 backlog): "
        + " · ".join(chunks)
    )


def format_review_panel_html(db: Session, lane_key: str | None = None) -> str:
    from app.data.aof_storage_hub_map import (
        GATEKEEPER_REVIEW_TOPIC_TITLE,
        category_emoji_for_network_key,
    )
    from app.services.export_flywheel_service import flywheel_mode, pool_depth_by_lane
    from app.services.quarantine_batch_review import lane_quarantine_buffer_count

    lane = _normalize_panel_lane_key(lane_key)
    waiting = count_quarantine_waiting(db, lane_key=lane)
    lines: list[str] = []

    if lane:
        emoji = category_emoji_for_network_key(lane)
        lines.append(
            f"🟡 <b>{html_escape(GATEKEEPER_REVIEW_TOPIC_TITLE)}</b> · {emoji} <b>{html_escape(lane)}</b>"
        )
        lines.append(f"Lane quarantine waiting: <b>{waiting}</b> media row(s)")
        lane_row = next(
            (r for r in pool_depth_by_lane(db) if str(r.get("network_key") or "") == lane),
            None,
        )
        if lane_row:
            depth = int(lane_row.get("approved_depth") or 0)
            suffix = "🟠" if lane_row.get("backlog_pressure") else ""
            mode = html_escape(flywheel_mode())
            lines.append(f"Pool approved (<code>{mode}</code>): <b>{depth}</b>{suffix}")
        buf = lane_quarantine_buffer_count(lane)
        if buf > 0:
            lines.append(f"Q&A batch buffer (not yet posted): <b>{buf}</b>")
        lines.append(
            f"<i>Bulk approve assigns <b>{html_escape(lane)}</b> to all waiting rows "
            f"(max {bulk_approve_max()} per run).</i>"
        )
    else:
        buffered = inbox_quarantine_buffer_count()
        lines.append(f"🟡 <b>{html_escape(GATEKEEPER_REVIEW_TOPIC_TITLE)}</b>")
        lines.append(f"Waiting quarantine: <b>{waiting}</b> media row(s)")
        lines.append(format_lane_pool_depth_html(db))
        if buffered > 0:
            lines.append(
                f"Inbox buffer (not yet album-posted): <b>{buffered}</b> — use /intake → Flush inbox albums first."
            )
        try:
            from app.data.aof_storage_hub_map import CONTENT_LANE_NETWORK_KEYS

            lane_bufs = []
            for lk in sorted(CONTENT_LANE_NETWORK_KEYS):
                if lk in ("inbox", "packs"):
                    continue
                n = lane_quarantine_buffer_count(lk)
                if n > 0:
                    lane_bufs.append(f"{lk}:{n}")
            if lane_bufs:
                lines.append(f"Lane Q&A buffers: <code>{', '.join(lane_bufs[:10])}</code>")
        except Exception:
            pass
        lines.append(
            f"<i>Bulk approve uses auto lane from source topic (max {bulk_approve_max()} per run). "
            f"Per-card lane emoji picks still apply when you approve one-by-one.</i>"
        )
    return "\n".join(lines)


def review_panel_keyboard(*, waiting: int, lane_key: str | None = None) -> dict[str, Any]:
    lane = _normalize_panel_lane_key(lane_key)
    rows: list[list[dict[str, str]]] = []
    if waiting > 0:
        label_lane = f" {lane.upper()}" if lane else ""
        rows.append(
            [
                {
                    "text": f"✅ Approve all{label_lane} ({waiting})",
                    "callback_data": panel_approve_callback(lane),
                }
            ]
        )
    rows.append([{"text": "🔄 Refresh", "callback_data": panel_refresh_callback(lane)}])
    if lane:
        rows.append([{"text": "📋 All lanes", "callback_data": CALLBACK_PANEL_OPEN}])
    return {"inline_keyboard": rows}


def review_panel_confirm_keyboard(*, waiting: int, lane_key: str | None = None) -> dict[str, Any]:
    lane = _normalize_panel_lane_key(lane_key)
    return {
        "inline_keyboard": [
            [
                {
                    "text": f"✅ Confirm approve {waiting}",
                    "callback_data": panel_approve_confirm_callback(lane),
                },
                {"text": "Cancel", "callback_data": panel_cancel_callback(lane)},
            ]
        ]
    }


def operator_approve_all_waiting(
    db: Session,
    *,
    operator_id: int | None = None,
    limit: int | None = None,
    lane_key: str | None = None,
) -> dict[str, Any]:
    lane = _normalize_panel_lane_key(lane_key)
    ids = list_quarantine_waiting_ids(db, limit=limit, lane_key=lane)
    if not ids:
        return {"ok": True, "approved": 0, "total": 0, "skipped": 0, "media_ids": [], "lane_key": lane}

    approved = 0
    skipped = 0
    results: list[dict[str, Any]] = []
    bulk_lanes = [lane] if lane else None
    for mid in ids:
        out = operator_approve_media(db, mid, operator_id=operator_id, lane_keys=bulk_lanes)
        results.append(out)
        if out.get("ok"):
            approved += 1
        else:
            skipped += 1
    return {
        "ok": approved > 0 or skipped == 0,
        "approved": approved,
        "skipped": skipped,
        "total": len(ids),
        "media_ids": ids,
        "lane_key": lane,
        "results": results,
    }


def operator_reject_media(
    db: Session,
    media_id: int,
    *,
    operator_id: int | None = None,
) -> dict[str, Any]:
    from app.models.media import Media

    media = db.query(Media).filter(Media.id == int(media_id)).first()
    if not media:
        return {"ok": False, "reason": "not_found"}

    media.status = "rejected"
    from app.services.gatekeeper_lane_picker import clear_picked_lanes

    clear_picked_lanes(media_id)
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


def resolve_preview_copy_target(media: Any) -> dict[str, Any] | None:
    """
    Resolve Bot API copyMessage source for a quarantined Media row.
    Prefer Storage Hub messages (indexed with telegram_message_id).
    """
    msg_id = int(getattr(media, "telegram_message_id", 0) or 0)
    if msg_id <= 0:
        return None

    src = (getattr(media, "source_channel", None) or "").strip()
    chat_id: str | int = STORAGE_HUB_IDENT
    source_thread_id: int | None = None

    m = _TOPIC_SOURCE_RE.search(src)
    if m:
        chat_id = m.group("chat")
        source_thread_id = int(m.group("thread"))
    elif src.startswith("-100") or (src.lstrip("-").isdigit() and len(src) >= 10):
        chat_id = src if src.startswith("-") else f"-{src}"
    elif STORAGE_HUB_IDENT.lstrip("-") in src.replace("telegram:", ""):
        chat_id = STORAGE_HUB_IDENT
    else:
        parsed = parse_source_channel_id(src)
        if parsed is not None:
            chat_id = parsed

    out: dict[str, Any] = {"from_chat_id": chat_id, "message_id": msg_id}
    if source_thread_id is not None:
        out["source_message_thread_id"] = source_thread_id
    return out


def review_preview_copy_enabled() -> bool:
    return (os.getenv("TBCC_GATEKEEPER_REVIEW_COPY_MEDIA") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _telegram_api_post(token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    with httpx.Client(timeout=25) as client:
        r = client.post(url, json=payload)
        data = r.json() if r.content else {}
        if r.status_code != 200 or not data.get("ok"):
            return {"ok": False, "error": str(data)[:400], "raw": data}
        return {"ok": True, "result": data.get("result") or {}}


def send_quarantine_review_message(db: Session, media_id: int) -> dict[str, Any]:
    """Post review card with media preview (copyMessage) when possible."""
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
    from app.services.gatekeeper_lane_picker import format_lane_pick_hint, lane_picker_enabled

    if lane_picker_enabled():
        text = f"{text}\n<i>{html_escape(format_lane_pick_hint([]))}</i>"
    from app.utils.telegram_forum import bot_api_forum_thread_id

    dest_chat = review_chat_id()
    dest_thread = bot_api_forum_thread_id(review_thread_id())
    default_lane = resolve_media_lane_key(db, media)
    keyboard = review_inline_keyboard(media_id, default_lane_key=default_lane)

    preview = resolve_preview_copy_target(media) if review_preview_copy_enabled() else None
    if preview:
        payload: dict[str, Any] = {
            "chat_id": dest_chat,
            "from_chat_id": preview["from_chat_id"],
            "message_id": int(preview["message_id"]),
            "caption": text,
            "parse_mode": "HTML",
            "reply_markup": keyboard,
        }
        if dest_thread:
            payload["message_thread_id"] = int(dest_thread)
        copy_out = _telegram_api_post(token, "copyMessage", payload)
        if copy_out.get("ok"):
            result = copy_out.get("result") or {}
            return {
                "ok": True,
                "media_id": media_id,
                "message_id": result.get("message_id"),
                "chat_id": result.get("chat", {}).get("id"),
                "preview": "copyMessage",
            }
        logger.info(
            "quarantine copyMessage failed media_id=%s — fallback to text (%s)",
            media_id,
            copy_out.get("error"),
        )

    payload = {
        "chat_id": dest_chat,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": keyboard,
        "disable_web_page_preview": True,
    }
    if dest_thread:
        payload["message_thread_id"] = int(dest_thread)

    text_out = _telegram_api_post(token, "sendMessage", payload)
    if not text_out.get("ok"):
        return {"ok": False, "error": text_out.get("error"), "media_id": media_id}
    result = text_out.get("result") or {}
    return {
        "ok": True,
        "media_id": media_id,
        "message_id": result.get("message_id"),
        "chat_id": result.get("chat", {}).get("id"),
        "preview": "text_only",
    }


def enqueue_quarantine_review(media_id: int) -> None:
    """Queue Telegram review card (non-blocking)."""
    if not review_notify_enabled():
        return
    try:
        from app.database.session import SessionLocal
        from app.models.media import Media
        from app.services.inbox_intake_review import (
            inbox_intake_enabled,
            is_inbox_media,
            post_inbox_quarantine_batch,
            queue_inbox_quarantine_media,
        )
        from app.services.quarantine_batch_review import (
            is_storage_lane_source,
            post_lane_quarantine_batch,
            queue_lane_quarantine_media,
        )

        with SessionLocal() as db:
            media = db.query(Media).filter(Media.id == int(media_id)).first()
            if not media:
                return
            if inbox_intake_enabled() and is_inbox_media(media):
                out = queue_inbox_quarantine_media(int(media_id))
                if out.get("flushing") and out.get("media_ids"):
                    post_inbox_quarantine_batch(db, list(out["media_ids"]))
                return
            if is_storage_lane_source(media):
                lane = resolve_media_lane_key(db, media) or ""
                out = queue_lane_quarantine_media(int(media_id), lane)
                if out.get("flushing") and out.get("media_ids"):
                    post_lane_quarantine_batch(db, lane, list(out["media_ids"]))
                return
    except Exception:
        logger.debug("quarantine batch route failed media_id=%s", media_id, exc_info=True)
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
