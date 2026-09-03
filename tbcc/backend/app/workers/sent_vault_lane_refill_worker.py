"""Beat task: recycle dry lane pools from SENT VAULT emoji archive."""

from __future__ import annotations

import logging
import os

from app.database.session import SessionLocal
from app.services.sent_vault_lane_refill import (
    refill_dry_lanes_from_sent_vault_sync,
    sent_vault_lane_refill_enabled,
)
from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.sent_vault_lane_refill_worker.refill_dry_lanes_from_sent_vault")
def refill_dry_lanes_from_sent_vault_task() -> dict:
    if not sent_vault_lane_refill_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    unpause = (os.getenv("TBCC_SENT_VAULT_REFILL_UNPAUSE") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    with SessionLocal() as db:
        report = refill_dry_lanes_from_sent_vault_sync(db, execute=True, unpause=unpause)
    logger.info(
        "sent vault lane refill: restored=%s would=%s",
        report.get("restored_total"),
        report.get("would_restore"),
    )
    return report
