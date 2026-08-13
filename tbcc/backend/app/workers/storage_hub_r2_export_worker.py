"""Celery: Storage Hub approved media → R2 (telegram queue)."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.storage_hub_r2_export_worker.export_storage_hub_media_to_r2")
def export_storage_hub_media_to_r2(
    since_id: int = 0,
    limit: int = 10,
    only_missing_r2: bool = True,
):
    from app.database.session import SessionLocal
    from app.services.storage_hub_r2_export import export_storage_hub_batch

    db = SessionLocal()
    try:
        out = export_storage_hub_batch(
            db,
            since_id=int(since_id or 0),
            limit=int(limit or 10),
            only_missing_r2=bool(only_missing_r2),
        )
        logger.info(
            "export_storage_hub_media_to_r2 since=%s exported=%s skipped=%s failed=%s next=%s",
            since_id,
            out.get("exported"),
            out.get("skipped"),
            out.get("failed"),
            out.get("next_since_id"),
        )
        return out
    finally:
        db.close()
