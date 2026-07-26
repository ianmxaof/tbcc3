"""Admission gates for listening relay — yield to overdue schedulers."""

from __future__ import annotations

import logging
import os

from sqlalchemy.orm import Session

from app.services.post_scheduler import count_overdue_scheduled_posts

logger = logging.getLogger(__name__)


def relay_pause_when_scheduler_overdue() -> bool:
    """When True (default), skip new relay sends while any recurring scheduler is past due."""
    return (os.getenv("TBCC_RELAY_PAUSE_WHEN_SCHEDULER_OVERDUE") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def relay_may_send_now(db: Session) -> bool:
    """False when schedulers are overdue and the pause gate is enabled."""
    if not relay_pause_when_scheduler_overdue():
        return True
    overdue = count_overdue_scheduled_posts(db, min_overdue_minutes=0.0)
    if overdue:
        logger.info(
            "listening relay admission: paused — %s scheduler(s) overdue (signature preserved)",
            len(overdue),
        )
        return False
    return True
