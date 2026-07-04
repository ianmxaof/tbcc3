"""Celery: Reddit JSON market probe + browse-intel drop sync."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.market_intel_worker.run_market_intel_probe")
def run_market_intel_probe():
    from app.services.erome_browse_intel import sync_from_drop_file
    from app.services.market_intel_probe import run_market_probes

    try:
        drop = sync_from_drop_file()
        probe = run_market_probes()
        report = {"ok": True, "drop_sync": drop, "probe": probe}
        logger.info("market intel probe: %s", report)
        return report
    except Exception as e:
        logger.exception("market intel probe failed")
        return {"ok": False, "error": str(e)[:300]}
