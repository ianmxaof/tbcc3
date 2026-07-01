"""Periodic Telethon view refresh for post_delivery_metrics."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


def view_refresh_beat_enabled() -> bool:
    return (os.getenv("TBCC_VIEW_REFRESH_BEAT_ENABLED") or "0").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def view_refresh_offpeak_hours_et() -> set[int]:
    raw = (os.getenv("TBCC_VIEW_REFRESH_OFFPEAK_HOURS_ET") or "2,3,4,5").strip()
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part) % 24)
        except ValueError:
            continue
    return out or {2, 3, 4, 5}


def view_refresh_offpeak_allowed() -> bool:
    from app.services.content_performance import analytics_timezone

    now_local = datetime.now(timezone.utc).astimezone(analytics_timezone())
    return now_local.hour in view_refresh_offpeak_hours_et()


@celery.task(name="app.workers.content_performance_worker.refresh_post_views")
def refresh_post_views(limit: int = 200):
    """Poll Telegram view counts for recent deliveries (GetMessagesViewsRequest)."""
    from app.database.session import SessionLocal
    from app.services.content_performance import performance_enabled, refresh_delivery_views_sync

    if not performance_enabled() or not view_refresh_beat_enabled():
        return {"ok": True, "skipped": True, "reason": "beat_disabled"}
    if not view_refresh_offpeak_allowed():
        return {"ok": True, "skipped": True, "reason": "outside_offpeak_hours_et"}

    db = SessionLocal()
    try:
        from app.services.content_signals import assess_growth_tick_eligibility

        eligibility = assess_growth_tick_eligibility(db)
        if not eligibility.get("can_refresh_views"):
            return {
                "ok": True,
                "skipped": True,
                "reason": eligibility.get("reason") or "insufficient_refreshable_deliveries",
                "eligibility": eligibility,
            }

        result = refresh_delivery_views_sync(db, limit=limit)
        if result.get("updated"):
            logger.info(
                "post view refresh: updated=%s checked=%s channels=%s",
                result.get("updated"),
                result.get("checked"),
                result.get("channels"),
            )
        return result
    finally:
        db.close()
