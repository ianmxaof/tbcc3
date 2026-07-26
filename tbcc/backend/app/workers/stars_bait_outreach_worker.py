"""Celery beat — paced Stars-bait DM outreach to known AOF users."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.stars_bait_outreach_worker.run_stars_bait_dm_pace_tick")
def run_stars_bait_dm_pace_tick():
    from app.database.session import SessionLocal
    from app.services.stars_bait_outreach import run_stars_bait_dm_pace_tick as _tick

    db = SessionLocal()
    try:
        result = _tick(db)
        if result.get("sent"):
            logger.info("stars bait DM pace: sent=%s skipped=%s failed=%s", result.get("sent"), result.get("skipped"), result.get("failed"))
        return result
    finally:
        db.close()
