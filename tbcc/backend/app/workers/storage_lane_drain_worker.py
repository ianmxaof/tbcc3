"""Celery — drain-this-lane: loop the deposit primitive until unique-dry or capped."""

from __future__ import annotations

import asyncio
import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.storage_lane_drain_worker.run_lane_drain")
def run_lane_drain_task(
    lane_key: str,
    *,
    token: str,
    chat_id: int,
    message_thread_id: int,
    status_message_id: int | None = None,
) -> dict:
    from app.services.storage_lane_drain import run_lane_drain

    out = asyncio.run(
        run_lane_drain(
            lane_key,
            token=token,
            chat_id=chat_id,
            message_thread_id=message_thread_id,
            status_message_id=status_message_id,
        )
    )
    if not out.get("ok"):
        logger.warning("lane drain task lane=%s %s", lane_key, out)
    return out
