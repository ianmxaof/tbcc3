"""Celery beat — weekly VIP direct mega pack drop."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.vip_weekly_mega_worker.run_weekly_vip_mega")
def run_weekly_vip_mega(*, force: bool = False) -> dict:
    from app.database.session import SessionLocal
    from app.services.aof_vip_weekly_mega import queue_weekly_vip_mega_drop

    db = SessionLocal()
    try:
        result = queue_weekly_vip_mega_drop(db, force=force)
        if result.get("ok") and not result.get("skipped"):
            logger.info("vip weekly mega queued: %s", result)
        return result
    finally:
        db.close()
