"""Celery beat — weekly build log to Loot Room PATCH NOTES + @aofmainhub."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.weekly_build_log_worker.run_weekly_build_log")
def run_weekly_build_log(*, force: bool = False) -> dict:
    from app.database.session import SessionLocal
    from app.services.weekly_build_log import queue_weekly_build_log_posts

    db = SessionLocal()
    try:
        result = queue_weekly_build_log_posts(db, force=force)
        if result.get("ok") and not result.get("skipped"):
            logger.info("weekly build log: %s", result)
        return result
    finally:
        db.close()
