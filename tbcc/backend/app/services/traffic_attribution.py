"""Deep-link traffic attribution — map ?start= payloads to source_ref, record touches."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.user_funnel_touch import UserFunnelTouch

logger = logging.getLogger(__name__)

_SRC_REF_RE = re.compile(r"^src_[a-z0-9_]{2,56}$")
_CHECKOUT_PLAN_RE = re.compile(r"^c(?:m)?(\d+)(?:_[A-Za-z0-9]{1,16})?$")
_REF_USER_RE = re.compile(r"^ref_(\d+)$", re.IGNORECASE)


def traffic_attribution_enabled() -> bool:
    return (os.getenv("TBCC_TRAFFIC_ATTRIBUTION_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def attribution_touch_model() -> str:
    raw = (os.getenv("TBCC_ATTRIBUTION_TOUCH_MODEL") or "first").strip().lower()
    return "last" if raw == "last" else "first"


def attribution_touch_ttl_days() -> int:
    raw = (os.getenv("TBCC_ATTRIBUTION_TOUCH_TTL_DAYS") or "30").strip()
    try:
        return max(1, min(365, int(raw)))
    except ValueError:
        return 30


def _truncate_payload(payload: str, *, limit: int = 128) -> str:
    return (payload or "").strip()[:limit]


def payload_to_source_ref(payload: str) -> str | None:
    """Map Telegram /start payload to a stable source_ref id."""
    raw = (payload or "").strip()
    if not raw:
        return None
    p = raw.lower()

    if _SRC_REF_RE.match(p):
        return p

    from app.services.stars_bait_copy import parse_bait_start_payload, StarsBaitProduct

    bait = parse_bait_start_payload(raw)
    if bait == StarsBaitProduct.LOOT_KEY:
        return "src_bait_loot"
    if bait == StarsBaitProduct.DAY_PASS:
        return "src_bait_day"
    if bait == StarsBaitProduct.SUBSCRIPTION:
        return "src_bait_vip"

    if p in ("loot_free",):
        return "src_loot_free"
    if p in ("loot", "menu_loot", "loot_keys"):
        return "src_loot_paid"

    if p.startswith("goblin_") and len(p) > len("goblin_"):
        return "src_goblin_claim"

    m_ref = _REF_USER_RE.match(raw)
    if m_ref:
        return f"src_ref_user_{m_ref.group(1)}"

    m_plan = _CHECKOUT_PLAN_RE.match(raw)
    if m_plan:
        return f"src_checkout_plan_{m_plan.group(1)}"

    from app.services.verify_funnel import parse_verify_start_payload

    verify = parse_verify_start_payload(raw)
    if verify:
        return f"src_verify_{verify}"

    from app.services.human_gate_pacing import parse_gate_start_payload

    gate = parse_gate_start_payload(raw)
    if gate:
        return f"src_gate_{gate}"

    if p.startswith("lootref_"):
        return "src_loot_referral"

    if p.startswith("spicy_") and len(p) > len("spicy_"):
        return f"src_{p}"

    if p == "spicy":
        return "src_spicy"

    return None


def record_traffic_touch(
    db: Session,
    telegram_user_id: int,
    payload: str,
    *,
    commit: bool = False,
) -> dict[str, Any]:
    """Upsert first/last touch for a user. Returns summary dict."""
    if not traffic_attribution_enabled():
        return {"ok": True, "skipped": "disabled"}

    uid = int(telegram_user_id)
    entry_payload = _truncate_payload(payload)
    source_ref = payload_to_source_ref(payload)
    if not source_ref:
        return {"ok": True, "skipped": "unmapped_payload", "payload": entry_payload}

    now = datetime.utcnow()
    row = db.query(UserFunnelTouch).filter(UserFunnelTouch.telegram_user_id == uid).first()
    if not row:
        row = UserFunnelTouch(
            telegram_user_id=uid,
            first_source_ref=source_ref,
            first_entry_payload=entry_payload,
            first_seen_at=now,
            last_source_ref=source_ref,
            last_entry_payload=entry_payload,
            last_seen_at=now,
            touch_count=1,
        )
        db.add(row)
    else:
        if not row.first_source_ref:
            row.first_source_ref = source_ref
            row.first_entry_payload = entry_payload
            row.first_seen_at = now
        row.last_source_ref = source_ref
        row.last_entry_payload = entry_payload
        row.last_seen_at = now
        row.touch_count = int(row.touch_count or 0) + 1

    if commit:
        db.commit()
    else:
        db.flush()

    return {
        "ok": True,
        "telegram_user_id": uid,
        "source_ref": source_ref,
        "touch_count": int(row.touch_count or 1),
    }


def touch_for_conversion(db: Session, telegram_user_id: int) -> UserFunnelTouch | None:
    """Return touch row used for subscription attribution (first or last per env)."""
    if not traffic_attribution_enabled():
        return None
    uid = int(telegram_user_id)
    row = db.query(UserFunnelTouch).filter(UserFunnelTouch.telegram_user_id == uid).first()
    if not row:
        return None
    ttl_days = attribution_touch_ttl_days()
    anchor = row.last_seen_at if attribution_touch_model() == "last" else row.first_seen_at
    if anchor and (datetime.utcnow() - anchor) > timedelta(days=ttl_days):
        return None
    return row


def resolve_attribution_for_user(db: Session, telegram_user_id: int) -> dict[str, str | None]:
    row = touch_for_conversion(db, telegram_user_id)
    if not row:
        return {"traffic_source_ref": None, "traffic_entry_payload": None}
    if attribution_touch_model() == "last":
        return {
            "traffic_source_ref": row.last_source_ref,
            "traffic_entry_payload": row.last_entry_payload,
        }
    return {
        "traffic_source_ref": row.first_source_ref,
        "traffic_entry_payload": row.first_entry_payload,
    }


def record_traffic_touch_from_bot(telegram_user_id: int, payload: str) -> None:
    """Sync helper for Telegram bot handlers."""
    if not traffic_attribution_enabled():
        return
    from app.database.session import SessionLocal

    db = SessionLocal()
    try:
        record_traffic_touch(db, int(telegram_user_id), payload, commit=True)
    except Exception:
        logger.debug("record_traffic_touch_from_bot failed uid=%s", telegram_user_id, exc_info=True)
    finally:
        db.close()


def conversions_by_source(db: Session, *, days: int = 30) -> dict[str, Any]:
    """Roll up subscription_created events by traffic_source_ref."""
    from app.models.growth_attribution_event import GrowthAttributionEvent
    from app.services.growth_attribution import EVENT_SUBSCRIPTION_CREATED

    since = datetime.utcnow() - timedelta(days=max(1, min(366, days)))
    rows = (
        db.query(GrowthAttributionEvent)
        .filter(
            GrowthAttributionEvent.created_at >= since,
            GrowthAttributionEvent.event_type == EVENT_SUBSCRIPTION_CREATED,
        )
        .all()
    )
    by_source: dict[str, dict[str, int]] = {}
    unattributed = 0
    unattributed_stars = 0
    for r in rows:
        ref = (r.traffic_source_ref or "").strip() or None
        stars = int(r.amount_stars or 0)
        if not ref:
            unattributed += 1
            unattributed_stars += stars
            continue
        bucket = by_source.setdefault(ref, {"subscriptions": 0, "stars": 0})
        bucket["subscriptions"] += 1
        bucket["stars"] += stars

    out_rows = [
        {"source_ref": ref, "subscriptions": data["subscriptions"], "stars": data["stars"]}
        for ref, data in sorted(by_source.items(), key=lambda x: -x[1]["stars"])
    ]
    return {
        "range_days": days,
        "conversions_by_source": out_rows,
        "unattributed_subscriptions": unattributed,
        "unattributed_stars": unattributed_stars,
    }
