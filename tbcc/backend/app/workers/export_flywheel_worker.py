"""Celery tasks for analytics-driven export flywheel."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.export_flywheel_worker.export_flywheel_tick")
def export_flywheel_tick(network_key: str | None = None):
    from app.database.session import SessionLocal
    from app.services.export_flywheel_service import flywheel_enabled, tick_observe

    if not flywheel_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    db = SessionLocal()
    try:
        result = tick_observe(db, push_inbox=True)
        result["network_key"] = network_key
        logger.info(
            "export flywheel tick mode=%s proposals=%s",
            result.get("mode"),
            (result.get("proposals") or {}).get("proposal_count"),
        )
        return result
    finally:
        db.close()
