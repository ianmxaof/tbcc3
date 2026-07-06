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


@celery.task(name="app.workers.storage_pool_seed_worker.backfill_thin_pools")
def backfill_thin_pools() -> dict:
    """Internal thin-lane backfill (Phase 1): seed only pools below the network median."""
    from app.database.session import SessionLocal
    from app.services.aof_growth_hub import (
        backfill_thin_pools_from_storage_hub,
        thin_pool_backfill_enabled,
    )

    if not thin_pool_backfill_enabled():
        return {"ok": True, "skipped": True, "reason": "TBCC_THIN_POOL_BACKFILL_ENABLED=0"}

    with SessionLocal() as db:
        report = backfill_thin_pools_from_storage_hub(db, execute=True)
    logger.info(
        "thin pool backfill: median=%s thin=%s",
        report.get("median"),
        report.get("thin_lanes"),
    )
    return report
