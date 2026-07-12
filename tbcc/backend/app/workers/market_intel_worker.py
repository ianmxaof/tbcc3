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


@celery.task(name="app.workers.market_intel_worker.run_weekly_market_intel_cycle")
def run_weekly_market_intel_cycle():
    """Monday weekly tick: fresh probe → evaluate cycle → optional gated post actions."""
    from app.database.session import SessionLocal
    from app.services.erome_browse_intel import sync_from_drop_file
    from app.services.market_intel_cycle import evaluate_weekly_cycle
    from app.services.market_intel_cycle_executor import execute_cycle_actions
    from app.services.market_intel_probe import run_market_probes

    try:
        drop = sync_from_drop_file()
        probe = run_market_probes()
        cycle = evaluate_weekly_cycle(force=False)
        actions: dict = {"skipped": True, "reason": "cycle_not_complete"}
        if cycle.get("complete"):
            db = SessionLocal()
            try:
                actions = execute_cycle_actions(db, cycle)
            finally:
                db.close()
        report = {
            "ok": True,
            "drop_sync": drop,
            "probe": probe,
            "cycle": {
                "week_id": cycle.get("week_id"),
                "complete": cycle.get("complete"),
                "confidence": cycle.get("confidence"),
                "leader_tag": cycle.get("leader_tag"),
                "reasons": cycle.get("reasons"),
            },
            "actions": actions,
        }
        logger.info("weekly market intel cycle: %s", report)
        return report
    except Exception as e:
        logger.exception("weekly market intel cycle failed")
        return {"ok": False, "error": str(e)[:300]}
