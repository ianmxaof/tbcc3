"""Celery: debounced Storage Hub lane auto-pipe into Q&A quarantine review."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.storage_auto_pipe_worker.run_lane_auto_pipe")
def run_lane_auto_pipe_task(lane_key: str) -> dict:
    from app.services.storage_auto_pipe import run_lane_auto_pipe

    out = run_lane_auto_pipe(str(lane_key or "").strip().lower())
    if not out.get("ok"):
        logger.info("lane auto-pipe lane=%s %s", lane_key, out)
    return out
