"""Celery: SCRP micro-pull into Storage Hub forum subtopics."""

from __future__ import annotations

import asyncio
import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.scrape_micro_pull_worker.run_lane_micro_pull")
def run_lane_micro_pull_task(lane_key: str) -> dict:
    """Pull one SCRP source batch into a lane Storage Hub topic."""
    from app.database.session import SessionLocal
    from app.services.scrape_micro_pull import micro_pull_enabled, run_lane_micro_pull
    from app.services.telegram_admin import run_telegram_io

    key = (lane_key or "").strip().lower()
    if not key:
        return {"ok": False, "reason": "lane_unset"}
    if not micro_pull_enabled():
        return {"ok": True, "skipped": True, "reason": "TBCC_SCRAPE_MICRO_PULL_ENABLED=0", "lane_key": key}

    async def _run(storage):
        with SessionLocal() as db:
            return await run_lane_micro_pull(storage, db, key)

    try:
        result = asyncio.run(run_telegram_io(_run))
    except Exception as e:
        logger.exception("micro_pull lane=%s failed", key)
        return {"ok": False, "lane_key": key, "error": str(e)[:400]}

    return {"ok": True, "lane_key": key, **result}


@celery.task(name="app.workers.scrape_micro_pull_worker.run_micro_pull_tick")
def run_micro_pull_tick_task() -> dict:
    from app.database.session import SessionLocal
    from app.services.scrape_micro_pull import micro_pull_enabled, run_micro_pull_tick
    from app.services.telegram_admin import run_telegram_io

    if not micro_pull_enabled():
        return {"ok": True, "skipped": True, "reason": "TBCC_SCRAPE_MICRO_PULL_ENABLED=0"}

    async def _run(storage):
        with SessionLocal() as db:
            return await run_micro_pull_tick(storage, db)

    try:
        result = asyncio.run(run_telegram_io(_run))
    except Exception as e:
        logger.exception("micro_pull tick failed")
        return {"ok": False, "error": str(e)[:400]}

    return {"ok": True, **result}


@celery.task(name="app.workers.scrape_micro_pull_worker.run_ass_micro_pull")
def run_ass_micro_pull_task() -> dict:
    """Legacy task name — delegates to lane-rotating tick."""
    return run_micro_pull_tick_task()
