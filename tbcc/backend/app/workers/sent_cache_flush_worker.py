"""Celery — flush pending SENT CACHE emoji album buffers."""

from __future__ import annotations

from app.workers.celery_app import celery


@celery.task(name="app.workers.sent_cache_flush_worker.flush_sent_cache_emoji_buffers")
def flush_sent_cache_emoji_buffers_task(*, force: bool = True) -> dict:
    from app.database.session import SessionLocal
    from app.services.import_job_runner import _run_on_worker_loop
    from app.services.storage_sent_cache import flush_all_sent_cache_emoji_buffers
    from app.services.telegram_admin import run_telegram_import_io

    async def _go(storage):
        with SessionLocal() as db:
            return await flush_all_sent_cache_emoji_buffers(storage, db, force=force)

    return _run_on_worker_loop(run_telegram_import_io(_go))
