"""Celery beat — subscription renewal + companion + loot re-engagement DMs."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.lifecycle_dm_worker.run_lifecycle_dm_tick")
def run_lifecycle_dm_tick():
    from app.database.session import SessionLocal
    from app.services.lifecycle_dm_outreach import run_lifecycle_dm_tick as _tick

    db = SessionLocal()
    try:
        result = _tick(db)
        if result.get("sent") or result.get("failed"):
            logger.info(
                "lifecycle DM tick: sent=%s skipped=%s failed=%s candidates=%s",
                result.get("sent"),
                result.get("skipped"),
                result.get("failed"),
                result.get("candidates"),
            )
        return result
    finally:
        db.close()
