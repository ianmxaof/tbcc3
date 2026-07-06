"""Celery: sync Erome album view counts into upload ledger."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.erome_analytics_worker.sync_erome_views")
def sync_erome_views():
    from app.database.session import SessionLocal
    from app.services.content_performance import sync_erome_views_to_delivery_ledger
    from app.services.erome_view_sync import sync_ledger_views
    from app.services.idle_service_governor import governed_service_active

    if not governed_service_active("erome_view_sync"):
        return {"ok": True, "skipped": "governed_idle"}

    try:
        from app.services.erome_browse_intel import sync_from_drop_file

        report = sync_ledger_views()
        report["browse_intel_drop"] = sync_from_drop_file()
        db = SessionLocal()
        try:
            bridge = sync_erome_views_to_delivery_ledger(db)
            report["delivery_ledger"] = bridge
        finally:
            db.close()
        logger.info("erome view sync: %s", report)
        return report
    except Exception as e:
        logger.exception("erome view sync failed")
        return {"ok": False, "error": str(e)[:300]}
