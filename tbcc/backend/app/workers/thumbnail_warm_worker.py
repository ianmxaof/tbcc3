"""Celery worker: warm dashboard thumbnails on the telegram queue (import session)."""

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.thumbnail_warm_worker.warm_media_thumbnails")
def warm_media_thumbnails(media_ids: list[int]):
    from app.services.import_job_runner import _run_on_worker_loop
    from app.services.thumb_cache_service import run_warm_thumbnails_async

    ids = [int(x) for x in (media_ids or []) if int(x) > 0][:60]
    if not ids:
        return {"warmed": 0, "cached": 0, "no_preview": 0, "missing": 0, "failed": 0}
    out = _run_on_worker_loop(run_warm_thumbnails_async(ids))
    logger.info("warm_media_thumbnails ids=%s -> %s", len(ids), out)
    return out
