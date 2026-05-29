"""Celery worker for staged imports (telegram queue — serialized Telegram uploads)."""

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.import_telegram_worker.process_import_job", bind=True)
def process_import_job(self, job_id: str):
    from app.services.import_job_runner import run_import_job_sync

    out = run_import_job_sync(job_id)
    if not out.get("ok"):
        logger.warning("process_import_job %s: %s", job_id, out)
    else:
        logger.info("process_import_job %s: %s", job_id, out.get("status"))
    return out
