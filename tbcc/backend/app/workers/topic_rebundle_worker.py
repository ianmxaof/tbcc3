"""Celery: rebundle loose chat/topic media into albums (any peer the admin session can see)."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.topic_rebundle_worker.rebundle_storage_topic_task")
def rebundle_storage_topic_task(
    *,
    message_thread_id: int | None = None,
    channel_ident: str | None = None,
    dry_run: bool = False,
    allow_partial: bool = True,
    delete_sources: bool | None = None,
):
    from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT
    from app.services.topic_rebundle_service import rebundle_storage_topic_loose_media_sync

    ident = (channel_ident or STORAGE_HUB_IDENT).strip()
    report = rebundle_storage_topic_loose_media_sync(
        message_thread_id=message_thread_id,
        channel_ident=ident,
        dry_run=bool(dry_run),
        allow_partial=bool(allow_partial),
        delete_sources=delete_sources,
    )
    logger.info(
        "topic rebundle peer=%s thread=%s dry_run=%s loose=%s albums_posted=%s partial=%s deleted=%s",
        ident,
        message_thread_id,
        dry_run,
        report.get("loose_count"),
        report.get("albums_posted"),
        report.get("partial_posted"),
        report.get("sources_deleted"),
    )
    return report
