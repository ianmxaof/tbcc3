"""Celery worker: emoji-factory split (+ optional Telegram upload / follow-up)."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.emoji_factory_worker.process_emoji_factory_job")
def process_emoji_factory_job(job_id: str) -> dict:
    from app.services.emoji_factory_async import execute_emoji_factory_job

    logger.info("emoji factory job start job_id=%s", job_id)
    try:
        result = execute_emoji_factory_job(job_id)
        logger.info("emoji factory job done job_id=%s status=%s", job_id, result.get("status"))
        return result
    except Exception as e:
        logger.exception("emoji factory job failed job_id=%s", job_id)
        from app.services.emoji_factory_job_status import job_dir_for, write_job_status

        try:
            write_job_status(job_dir_for(job_id), status="failed", stage="failed", error=str(e)[:500])
        except Exception:
            pass
        raise
