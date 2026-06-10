"""Celery worker for staged imports (telegram queue — serialized Telegram uploads)."""

import logging

from celery.signals import worker_shutdown

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@worker_shutdown.connect
def _import_worker_shutdown(**_kwargs) -> None:
    from app.services.import_job_runner import shutdown_import_worker_async

    shutdown_import_worker_async()


@celery.task(name="app.workers.import_telegram_worker.process_import_job", bind=True)
def process_import_job(self, job_id: str):
    from app.database.session import SessionLocal
    from app.models.import_job import ImportJob
    from app.services.import_job_runner import run_import_job_sync

    db = SessionLocal()
    try:
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        kind = (job.job_kind if job else None) or "bytes"
    finally:
        db.close()

    if kind == "channel":
        from app.services.channel_import_runner import run_channel_import_job_sync

        out = run_channel_import_job_sync(job_id)
    else:
        out = run_import_job_sync(job_id)
    if not out.get("ok"):
        logger.warning("process_import_job %s: %s", job_id, out)
    else:
        logger.info("process_import_job %s: %s", job_id, out.get("status"))
    return out
