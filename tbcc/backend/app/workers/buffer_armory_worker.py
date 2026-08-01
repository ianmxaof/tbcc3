"""Auto-refill Buffer X armory queues when depth falls below threshold."""

from __future__ import annotations

import logging
import os

from celery.signals import worker_ready

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


def _min_queue_depth() -> int:
    try:
        return max(1, min(16, int((os.getenv("TBCC_BUFFER_ARMORY_MIN_DEPTH") or "3").strip())))
    except ValueError:
        return 3


def _startup_refill_enabled() -> bool:
    return (os.getenv("TBCC_BUFFER_ARMORY_STARTUP_REFILL") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _startup_refill_countdown_s() -> int:
    try:
        return max(30, min(600, int((os.getenv("TBCC_BUFFER_ARMORY_STARTUP_DELAY_S") or "90").strip())))
    except ValueError:
        return 90


def _worker_should_run_startup_refill(hostname: str) -> bool:
    """Post-scheduler workers should not own Buffer queue stocking."""
    h = (hostname or "").lower()
    if "post@" in h or h.startswith("island-post@"):
        return False
    if h.startswith("scheduler@"):
        return False
    return True


@worker_ready.connect
def _schedule_buffer_armory_startup_refill(sender=None, **kwargs):
    if not _startup_refill_enabled():
        return
    from app.services.buffer_graphql import buffer_api_key

    if not buffer_api_key():
        return
    hostname = str(getattr(sender, "hostname", "") or "")
    if not _worker_should_run_startup_refill(hostname):
        return
    countdown = _startup_refill_countdown_s()
    refill_buffer_armory.apply_async(countdown=countdown, queue="celery")
    logger.info(
        "buffer armory: scheduled startup refill in %ss (worker=%s)",
        countdown,
        hostname or "?",
    )


@celery.task(name="app.workers.buffer_armory_worker.refill_buffer_armory")
def refill_buffer_armory():
    """Top up relay + scheduled buffer_x_queue and Buffer native X queue when below min depth."""
    from app.database.session import SessionLocal
    from app.models.listening_relay_settings import ListeningRelaySettings
    from app.models.scheduled_text_post import ScheduledTextPost
    from app.services.buffer_native_queue_refill import refill_buffer_native_queue
    from app.services.seed_aof_buffer_armory import (
        build_armory_queue_items,
        seed_relay_buffer_armory,
        seed_scheduled_buffer_armory,
        _eligible_buffer_mirror_posts,
    )

    min_depth = _min_queue_depth()
    items = build_armory_queue_items()
    if not items:
        logger.info("buffer armory refill: no armory templates")
        armory_report: dict = {"status": "empty_templates"}
    else:
        armory_report = {"relay_refilled": False, "scheduled_refilled": 0, "min_depth": min_depth}

    db = SessionLocal()
    try:
        if items:
            row = db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == 1).first()
            relay_depth = len(row.get_buffer_x_queue()) if row else 0
            if relay_depth < min_depth:
                seed_relay_buffer_armory(db, replace=False)
                armory_report["relay_refilled"] = True

            posts = db.query(ScheduledTextPost).filter(ScheduledTextPost.buffer_mirror_enabled.is_(True)).all()
            posts = _eligible_buffer_mirror_posts(db, posts)
            for post in posts:
                if len(post.get_buffer_x_queue()) < min_depth:
                    seed_scheduled_buffer_armory(db, post_id=int(post.id), replace=False)
                    armory_report["scheduled_refilled"] += 1
    finally:
        db.close()

    native_report = refill_buffer_native_queue()
    report = {"armory": armory_report, "native_queue": native_report}
    logger.info("buffer armory refill: %s", report)
    return report
