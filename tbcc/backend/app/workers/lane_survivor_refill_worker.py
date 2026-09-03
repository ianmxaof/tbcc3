"""Beat task: recycle posted/survivor pool media back into approved rotation."""

from __future__ import annotations

import logging
import os

from app.database.session import SessionLocal
from app.services.lane_survivor_refill import (
    lane_survivor_refill_enabled,
    refill_lanes_from_survivors_sync,
)
from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.lane_survivor_refill_worker.refill_lanes_from_survivors")
def refill_lanes_from_survivors_task() -> dict:
    if not lane_survivor_refill_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    target = int(os.getenv("TBCC_LANE_SURVIVOR_REFILL_TARGET") or "60")
    probe_cap = int(os.getenv("TBCC_LANE_SURVIVOR_REFILL_PROBE_CAP") or "120")
    unpause = (os.getenv("TBCC_LANE_SURVIVOR_REFILL_UNPAUSE") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    with SessionLocal() as db:
        report = refill_lanes_from_survivors_sync(
            db,
            target=target,
            probe_cap=probe_cap,
            execute=True,
            unpause=unpause,
        )
        try:
            from app.services.sent_vault_lane_refill import (
                refill_dry_lanes_from_sent_vault_sync,
                sent_vault_lane_refill_enabled,
            )

            if sent_vault_lane_refill_enabled():
                vault = refill_dry_lanes_from_sent_vault_sync(db, execute=True, unpause=unpause)
                report["sent_vault"] = vault
                report["restored_total"] = int(report.get("restored_total") or 0) + int(
                    vault.get("restored_total") or 0
                )
        except Exception as e:
            logger.warning("sent vault lane refill after survivor failed: %s", e)
            report["sent_vault_error"] = str(e)[:200]
    logger.info(
        "lane survivor refill: restored=%s probed=%s",
        report.get("restored_total"),
        report.get("probed"),
    )
    return report
