"""Periodic network liveness: milestone FOMO posts to Loot Room commons."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.network_liveness_worker.post_milestone_fomo")
def post_milestone_fomo():
    from app.database.session import SessionLocal
    from app.services.aof_network_liveness import post_milestone_fomo_to_main

    db = SessionLocal()
    try:
        result = post_milestone_fomo_to_main(db)
        logger.info("network liveness milestone FOMO: %s", result)
        return result
    finally:
        db.close()
