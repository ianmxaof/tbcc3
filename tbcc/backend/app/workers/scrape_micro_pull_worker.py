"""Celery: SCRP micro-pull into Storage Hub (pilot ASS lane)."""

from __future__ import annotations

import asyncio
import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.scrape_micro_pull_worker.run_ass_micro_pull")
def run_ass_micro_pull_task() -> dict:
    from app.database.session import SessionLocal
    from app.services.scrape_micro_pull import micro_pull_enabled, run_ass_micro_pull
    from app.services.telegram_admin import run_telegram_io

    if not micro_pull_enabled():
        return {"ok": True, "skipped": True, "reason": "TBCC_SCRAPE_MICRO_PULL_ENABLED=0"}

    async def _run(storage):
        with SessionLocal() as db:
            return await run_ass_micro_pull(storage, db)

    try:
        result = asyncio.run(run_telegram_io(_run))
    except Exception as e:
        logger.exception("ass micro_pull failed")
        return {"ok": False, "error": str(e)[:400]}

    return {"ok": True, **result}
