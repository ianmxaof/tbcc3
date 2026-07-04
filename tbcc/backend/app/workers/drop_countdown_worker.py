"""Celery tasks for drop countdown ETA chain."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


def enqueue_drop_countdown_chain(session_id: int, *, drop_at: datetime) -> dict:
    from app.services.drop_countdown import COUNTDOWN_TICKS_MINUTES, upcoming_ticks

    if drop_at.tzinfo is None:
        drop_at = drop_at.replace(tzinfo=timezone.utc)

    queued: list[dict] = []
    for minutes_left, eta in upcoming_ticks(drop_at):
        result = drop_countdown_tick.apply_async(
            args=[int(session_id), minutes_left if minutes_left > 0 else 0],
            eta=eta,
        )
        queued.append(
            {
                "minutes_left": minutes_left,
                "eta": eta.isoformat(),
                "task_id": result.id,
            }
        )
    logger.info("drop countdown session=%s queued %s ticks", session_id, len(queued))
    return {"session_id": session_id, "ticks": queued, "tick_minutes": list(COUNTDOWN_TICKS_MINUTES)}


@celery.task(name="app.workers.drop_countdown_worker.drop_countdown_tick")
def drop_countdown_tick(session_id: int, minutes_left: int = 0):
    from app.database.session import SessionLocal
    from app.services.drop_countdown import tick_drop_countdown

    db = SessionLocal()
    try:
        if minutes_left <= 0:
            return tick_drop_countdown(db, int(session_id), minutes_left=None)
        return tick_drop_countdown(db, int(session_id), minutes_left=int(minutes_left))
    finally:
        db.close()
