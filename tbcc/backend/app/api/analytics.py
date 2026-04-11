"""Basic analytics for subscriptions, revenue, and outbound post metrics."""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.channel import Channel
from app.models.post_outbound_event import PostOutboundEvent
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan

router = APIRouter()


@router.get("/subscriptions")
def subscription_analytics(db: Session = Depends(get_db)):
    """Return subscription counts and revenue (Stars)."""
    total = db.query(Subscription).count()
    active = db.query(Subscription).filter(Subscription.status == "active").count()
    expired = db.query(Subscription).filter(Subscription.status == "expired").count()
    cancelled = db.query(Subscription).filter(Subscription.status == "cancelled").count()

    # Revenue: sum of amount_stars, fallback to plan.price_stars for legacy rows
    revenue_result = (
        db.query(func.coalesce(func.sum(Subscription.amount_stars), 0))
        .filter(Subscription.status.in_(["active", "expired"]))
        .scalar()
    )
    revenue_stars = int(revenue_result or 0)

    # For rows without amount_stars, add plan price (legacy data)
    legacy_subs = (
        db.query(SubscriptionPlan.price_stars)
        .join(Subscription, Subscription.plan_id == SubscriptionPlan.id)
        .filter(
            Subscription.status.in_(["active", "expired"]),
            Subscription.amount_stars.is_(None),
        )
        .all()
    )
    legacy_revenue = sum((p[0] or 0) for p in legacy_subs)
    revenue_stars += legacy_revenue

    return {
        "total_subscriptions": total,
        "active": active,
        "expired": expired,
        "cancelled": cancelled,
        "revenue_stars": revenue_stars,
    }


def _day_key(dt: datetime | None) -> str:
    if not dt:
        return ""
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt.date().isoformat()


@router.get("/post-events")
def list_post_events(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Recent outbound post log (scheduled sends + pool album posts)."""
    q = (
        db.query(PostOutboundEvent)
        .order_by(PostOutboundEvent.id.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = q.all()
    ch_ids = {r.channel_id for r in rows if r.channel_id}
    names: dict[int, str] = {}
    if ch_ids:
        for c in db.query(Channel).filter(Channel.id.in_(ch_ids)).all():
            names[c.id] = c.name or c.identifier or str(c.id)
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
                "event_type": r.event_type,
                "channel_id": r.channel_id,
                "channel_name": names.get(r.channel_id) if r.channel_id else None,
                "scheduled_post_id": r.scheduled_post_id,
                "pool_id": r.pool_id,
                "ok": r.ok,
                "error_message": r.error_message,
            }
        )
    return {"items": out, "limit": limit, "offset": offset}


@router.get("/post-events/summary")
def post_events_summary(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=366),
):
    """Aggregates for charts: counts by day and channel over the last `days` days."""
    start = datetime.utcnow() - timedelta(days=days)
    rows = db.query(PostOutboundEvent).filter(PostOutboundEvent.created_at >= start).all()

    totals: dict[str, int] = defaultdict(int)
    by_day: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_channel: dict[int, int] = defaultdict(int)

    for r in rows:
        totals[r.event_type] += 1
        totals["_all"] += 1
        if r.ok:
            totals["_ok"] += 1
        else:
            totals["_failed"] += 1
        dk = _day_key(r.created_at)
        if dk:
            by_day[dk][r.event_type] += 1
            by_day[dk]["_count"] += 1
        if r.channel_id:
            by_channel[r.channel_id] += 1

    day_list = sorted(by_day.keys())
    by_day_out = []
    for d in day_list:
        m = by_day[d]
        by_day_out.append(
            {
                "date": d,
                "scheduled_post_sent": m.get("scheduled_post_sent", 0),
                "pool_album_posted": m.get("pool_album_posted", 0),
                "count": m.get("_count", 0),
            }
        )

    ch_rows = []
    if by_channel:
        ch_ids = list(by_channel.keys())
        ch_map = {c.id: c for c in db.query(Channel).filter(Channel.id.in_(ch_ids)).all()}
        for cid, cnt in sorted(by_channel.items(), key=lambda x: -x[1]):
            ch = ch_map.get(cid)
            ch_rows.append(
                {
                    "channel_id": cid,
                    "channel_name": (ch.name or ch.identifier) if ch else str(cid),
                    "count": cnt,
                }
            )

    return {
        "range_days": days,
        "totals": {
            "scheduled_post_sent": totals.get("scheduled_post_sent", 0),
            "pool_album_posted": totals.get("pool_album_posted", 0),
            "all": totals.get("_all", 0),
            "ok": totals.get("_ok", 0),
            "failed": totals.get("_failed", 0),
        },
        "by_day": by_day_out,
        "by_channel": ch_rows,
    }
