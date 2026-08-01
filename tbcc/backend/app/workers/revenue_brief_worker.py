"""Celery beat — daily LLM revenue brief to Secretary inbox."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.revenue_brief_worker.run_revenue_brief")
def run_revenue_brief(*, force: bool = False) -> dict:
    from app.database.session import SessionLocal
    from app.services.revenue_brief import send_revenue_brief

    db = SessionLocal()
    try:
        result = send_revenue_brief(db, force=force)
        if result.get("ok") and not result.get("skipped"):
            logger.info("revenue brief: %s", result)
        return result
    finally:
        db.close()
