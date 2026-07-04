"""Celery: small-batch Storage Hub topic → AOF channel pool imports."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.storage_pool_seed_worker.seed_pools_from_storage_hub")
def seed_pools_from_storage_hub() -> dict:
    from app.database.session import SessionLocal
    from app.services.aof_growth_hub import (
        queue_storage_hub_deposits,
        storage_pool_seed_batch_size,
        storage_pool_seed_enabled,
    )

    if not storage_pool_seed_enabled():
        return {"ok": True, "skipped": True, "reason": "TBCC_STORAGE_POOL_SEED_ENABLED=0"}

    batch = storage_pool_seed_batch_size()
    with SessionLocal() as db:
        report = queue_storage_hub_deposits(
            db,
            limit=batch,
            content_lanes_only=True,
            media_types="both",
        )
    logger.info(
        "storage pool seed queued %s jobs (%s/topic)",
        report.get("matched_count"),
        batch,
    )
    return report
