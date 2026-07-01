"""Growth conversion attribution with ambient scheduler context."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.growth_attribution_event import GrowthAttributionEvent
from app.models.post_delivery_metric import PostDeliveryMetric
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.content_performance import analytics_timezone_label, latest_delivery_for_attribution

logger = logging.getLogger(__name__)

EVENT_LOOT_ROLL = "loot_roll"
EVENT_LOOT_FREE_PULL = "loot_free_pull"
EVENT_SUBSCRIPTION_CREATED = "subscription_created"
EVENT_REFERRAL_RECORDED = "referral_recorded"
EVENT_EROME_ALBUM_PUBLISHED = "erome_album_published"


def attribution_enabled() -> bool:
    return (os.getenv("TBCC_GROWTH_ATTRIBUTION_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def attribution_lookback_hours() -> int:
    raw = (os.getenv("TBCC_GROWTH_ATTRIBUTION_LOOKBACK_HOURS") or "6").strip()
    try:
        return max(1, min(168, int(raw)))
    except ValueError:
        return 6


def build_growth_context_snapshot(db: Session, *, lookback_hours: int | None = None) -> dict[str, Any]:
    hours = lookback_hours or attribution_lookback_hours()
    since = datetime.utcnow() - timedelta(hours=hours)

    recent_deliveries = (
        db.query(PostDeliveryMetric)
        .filter(PostDeliveryMetric.created_at >= since)
        .order_by(PostDeliveryMetric.id.desc())
        .limit(15)
        .all()
    )
    active_schedulers = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.interval_minutes.isnot(None))
        .order_by(ScheduledTextPost.id.asc())
        .limit(40)
        .all()
    )

    return {
        "snapshot_at": datetime.utcnow().isoformat() + "Z",
        "lookback_hours": hours,
        "analytics_tz": analytics_timezone_label(),
        "recent_deliveries": [
            {
                "delivery_metric_id": d.id,
                "scheduled_post_id": d.scheduled_post_id,
                "channel_id": d.channel_id,
                "scheduler_name": d.scheduler_name,
                "caption_slot_index": d.caption_slot_index,
                "posted_hour_local": d.posted_hour_local,
                "views_latest": d.views_latest,
                "created_at": d.created_at.isoformat() + "Z" if d.created_at else None,
            }
            for d in recent_deliveries
        ],
        "active_scheduler_names": [
            (s.name or f"post#{s.id}").strip() for s in active_schedulers if (s.name or "").strip()
        ],
    }


def record_growth_attribution(
    db: Session,
    *,
    event_type: str,
    telegram_user_id: int | None = None,
    amount_stars: int | None = None,
    plan_id: int | None = None,
    channel_id: int | None = None,
    scheduled_post_id: int | None = None,
    delivery_metric_id: int | None = None,
    caption_slot_index: int | None = None,
    posted_hour_local: int | None = None,
    extra: dict[str, Any] | None = None,
    attach_latest_delivery: bool = True,
) -> GrowthAttributionEvent | None:
    if not attribution_enabled():
        return None

    ctx = build_growth_context_snapshot(db)
    if extra:
        ctx["extra"] = extra

    if attach_latest_delivery and delivery_metric_id is None and scheduled_post_id is None:
        touch = latest_delivery_for_attribution(db, lookback_hours=attribution_lookback_hours())
        if touch:
            delivery_metric_id = touch.id
            scheduled_post_id = touch.scheduled_post_id
            caption_slot_index = touch.caption_slot_index
            posted_hour_local = touch.posted_hour_local
            channel_id = channel_id or touch.channel_id

    row = GrowthAttributionEvent(
        created_at=datetime.utcnow(),
        event_type=event_type,
        telegram_user_id=int(telegram_user_id) if telegram_user_id is not None else None,
        amount_stars=int(amount_stars) if amount_stars is not None else None,
        plan_id=int(plan_id) if plan_id is not None else None,
        channel_id=int(channel_id) if channel_id is not None else None,
        scheduled_post_id=int(scheduled_post_id) if scheduled_post_id is not None else None,
        delivery_metric_id=int(delivery_metric_id) if delivery_metric_id is not None else None,
        caption_slot_index=int(caption_slot_index) if caption_slot_index is not None else None,
        posted_hour_local=int(posted_hour_local) if posted_hour_local is not None else None,
        context_json=json.dumps(ctx, separators=(",", ":"), default=str),
    )
    db.add(row)
    try:
        db.flush()
    except Exception:
        logger.debug("growth attribution flush failed", exc_info=True)
        return None
    return row


def attribution_summary(db: Session, *, days: int = 30) -> dict[str, Any]:
    since = datetime.utcnow() - timedelta(days=max(1, min(366, days)))
    rows = (
        db.query(GrowthAttributionEvent)
        .filter(GrowthAttributionEvent.created_at >= since)
        .all()
    )

    by_type: dict[str, int] = {}
    by_hour: dict[int, int] = {}
    stars_total = 0
    for r in rows:
        by_type[r.event_type] = by_type.get(r.event_type, 0) + 1
        if r.posted_hour_local is not None:
            by_hour[int(r.posted_hour_local)] = by_hour.get(int(r.posted_hour_local), 0) + 1
        if r.event_type == EVENT_SUBSCRIPTION_CREATED and r.amount_stars:
            stars_total += int(r.amount_stars)

    hour_rows = [{"hour_local": h, "count": by_hour.get(h, 0)} for h in range(24)]
    top_hours = sorted(by_hour.items(), key=lambda x: -x[1])[:5]

    return {
        "range_days": days,
        "timezone": analytics_timezone_label(),
        "totals_by_type": by_type,
        "subscription_stars_total": stars_total,
        "conversions_by_hour_local": hour_rows,
        "top_conversion_hours_local": [{"hour": h, "count": c} for h, c in top_hours],
    }


def list_attribution_events(
    db: Session,
    *,
    days: int = 30,
    limit: int = 100,
    offset: int = 0,
    event_type: str | None = None,
) -> dict[str, Any]:
    since = datetime.utcnow() - timedelta(days=max(1, min(366, days)))
    q = db.query(GrowthAttributionEvent).filter(GrowthAttributionEvent.created_at >= since)
    if event_type:
        q = q.filter(GrowthAttributionEvent.event_type == event_type.strip())
    total = q.count()
    rows = q.order_by(GrowthAttributionEvent.id.desc()).offset(offset).limit(max(1, min(500, limit))).all()

    items = []
    for r in rows:
        ctx = None
        if r.context_json:
            try:
                ctx = json.loads(r.context_json)
            except (json.JSONDecodeError, TypeError):
                ctx = None
        items.append(
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
                "event_type": r.event_type,
                "telegram_user_id": int(r.telegram_user_id) if r.telegram_user_id else None,
                "amount_stars": r.amount_stars,
                "plan_id": r.plan_id,
                "channel_id": r.channel_id,
                "scheduled_post_id": r.scheduled_post_id,
                "delivery_metric_id": r.delivery_metric_id,
                "caption_slot_index": r.caption_slot_index,
                "posted_hour_local": r.posted_hour_local,
                "context": ctx,
            }
        )
    return {"range_days": days, "total": total, "limit": limit, "offset": offset, "items": items}
