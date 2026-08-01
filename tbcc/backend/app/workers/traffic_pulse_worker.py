"""Beat task: Traffic Pulse digest DM every N minutes."""

from __future__ import annotations

import logging

from app.services.traffic_pulse import send_traffic_pulse_digest, traffic_pulse_enabled
from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.traffic_pulse_worker.send_traffic_pulse_digest")
def send_traffic_pulse_digest_task() -> dict:
    if not traffic_pulse_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}
    out = send_traffic_pulse_digest()
    logger.info("traffic pulse digest: %s", out)
    return out
