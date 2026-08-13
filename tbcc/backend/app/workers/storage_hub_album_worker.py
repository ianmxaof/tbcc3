"""Celery — flush Storage Hub album intake buffers (operator /intake panel)."""

from __future__ import annotations

from app.workers.celery_app import celery


@celery.task(name="app.workers.storage_hub_album_worker.flush_storage_hub_album_buffers")
def flush_storage_hub_album_buffers_task(*, force: bool = True) -> dict:
    from app.services.storage_hub_album_intake import flush_all_storage_hub_album_buffers

    return flush_all_storage_hub_album_buffers(force=force)
