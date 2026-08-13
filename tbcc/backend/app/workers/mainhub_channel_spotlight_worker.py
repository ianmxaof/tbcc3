"""Daily @aofmainhub channel spotlight — Celery beat (hour-gated)."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.mainhub_channel_spotlight_worker.send_mainhub_channel_spotlight")
def send_mainhub_channel_spotlight(force: bool = False):
    """Post one channel-of-the-day spotlight to @aofmainhub (default 15:00 UTC)."""
    from app.database.session import SessionLocal
    from app.services.mainhub_channel_spotlight import queue_mainhub_channel_spotlight

    db = SessionLocal()
    try:
        report = queue_mainhub_channel_spotlight(db, force=force)
        if report.get("skipped"):
            logger.debug("Mainhub spotlight skipped: %s", report.get("reason"))
        elif not report.get("ok"):
            logger.warning("Mainhub spotlight failed: %s", report)
        return report
    except Exception:
        logger.exception("Mainhub channel spotlight worker failed")
        raise
    finally:
        db.close()


@celery.task(name="app.workers.mainhub_channel_spotlight_worker.refresh_lane_of_the_day_liveness")
def refresh_lane_of_the_day_liveness_task():
    """UTC midnight refresh — sync Loot Room liveness copy to today's lane."""
    from app.database.session import SessionLocal
    from app.services.lane_of_the_day import refresh_lane_of_the_day_liveness

    db = SessionLocal()
    try:
        report = refresh_lane_of_the_day_liveness(db, execute=True)
        db.commit()
        logger.info("Lane-of-the-day liveness refresh: %s", report)
        return report
    except Exception:
        logger.exception("Lane-of-the-day liveness refresh failed")
        raise
    finally:
        db.close()
