"""Periodic income ledger refresh (Celery Beat)."""

from __future__ import annotations

import logging
import os

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.income_poll_worker.poll_income_sources")
def poll_income_sources():
    """Light poll: backfill internal subs + sync external sources when credentials exist."""
    from app.database.session import SessionLocal
    from app.services.income_sync import income_poll_enabled, run_income_poll

    if not income_poll_enabled():
        return {"ok": True, "skipped": True, "reason": "TBCC_INCOME_POLL_ENABLED=0"}

    light = (os.getenv("TBCC_INCOME_POLL_LIGHT") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )

    db = SessionLocal()
    try:
        result = run_income_poll(db, light=light)
        totals = (result.get("totals") or {}) if isinstance(result, dict) else {}
        logger.info(
            "income poll: usd=%s entries=%s light=%s",
            totals.get("usd"),
            totals.get("entry_count"),
            light,
        )
        return result
    except Exception as e:
        logger.exception("income poll failed: %s", e)
        from app.services.income_sync import save_income_poll_status
        from datetime import datetime

        save_income_poll_status(
            {
                "ok": False,
                "last_poll_at": datetime.utcnow().isoformat() + "Z",
                "last_poll_ok": False,
                "error": str(e),
            }
        )
        raise
    finally:
        db.close()
