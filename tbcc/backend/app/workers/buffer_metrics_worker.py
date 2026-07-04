"""Celery: sync Buffer post metrics into post_delivery_metrics."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.buffer_metrics_worker.sync_buffer_metrics")
def sync_buffer_metrics(limit: int = 40):
    from app.database.session import SessionLocal
    from app.services.buffer_metrics_sync import buffer_metrics_sync_enabled, sync_buffer_post_metrics

    if not buffer_metrics_sync_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    db = SessionLocal()
    try:
        report = sync_buffer_post_metrics(db, limit=limit)
        if report.get("updated"):
            logger.info("buffer metrics sync: %s", report)
        return report
    finally:
        db.close()
