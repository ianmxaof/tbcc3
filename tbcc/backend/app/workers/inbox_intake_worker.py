"""Celery: intake scheduler tick + inbox channel/subtopic deposits."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.inbox_intake_worker.run_intake_schedule_tick")
def run_intake_schedule_tick(*, force: bool = False) -> dict:
    """Deposit due lanes (all content lanes + inbox) on configurable cadence."""
    from app.database.session import SessionLocal
    from app.services.aof_growth_hub import queue_storage_hub_deposits
    from app.services.intake_scheduler import (
        get_batch_size,
        intake_scheduler_enabled,
        lane_due_for_run,
        mark_lane_run,
        scheduler_lane_keys,
    )
    from app.services.inbox_intake_review import flush_pending_inbox_quarantine
    from app.services.storage_topic_deposit import queue_inbox_channel_deposit

    if not intake_scheduler_enabled():
        return {"ok": True, "skipped": True, "reason": "TBCC_INTAKE_SCHEDULER_ENABLED=0"}

    due_lanes: list[str] = []
    for lane in scheduler_lane_keys():
        if lane_due_for_run(lane, force=force):
            due_lanes.append(lane)

    if not due_lanes:
        return {"ok": True, "skipped": True, "reason": "no_lanes_due"}

    reports: list[dict] = []
    with SessionLocal() as db:
        content_lanes = [k for k in due_lanes if k != "inbox"]
        if content_lanes:
            for lane in content_lanes:
                batch = get_batch_size(lane)
                report = queue_storage_hub_deposits(
                    db,
                    limit=batch,
                    topic_keys=[lane],
                    media_types="both",
                    content_lanes_only=False,
                    include_topic_mirror=False,
                )
                reports.append({"lane_key": lane, "batch": batch, **report})
                mark_lane_run(lane)

        if "inbox" in due_lanes:
            batch = get_batch_size("inbox")
            topic_report = queue_storage_hub_deposits(
                db,
                limit=batch,
                topic_keys=["inbox"],
                media_types="both",
                content_lanes_only=False,
                include_topic_mirror=False,
            )
            channel_report = queue_inbox_channel_deposit(db, limit=batch, media_types="both")
            reports.append(
                {
                    "lane_key": "inbox",
                    "batch": batch,
                    "topic": topic_report,
                    "channel": channel_report,
                }
            )
            mark_lane_run("inbox")

    flush = flush_pending_inbox_quarantine(force=False)
    try:
        flush_inbox_quarantine_albums.apply_async(countdown=120, kwargs={"force": True})
    except Exception:
        logger.debug("deferred inbox album flush enqueue failed", exc_info=True)
    logger.info("intake tick due=%s reports=%s flush=%s", due_lanes, len(reports), flush.get("ok"))
    return {"ok": True, "due_lanes": due_lanes, "reports": reports, "inbox_flush": flush}


@celery.task(name="app.workers.inbox_intake_worker.run_inbox_intake_now")
def run_inbox_intake_now(*, batch: int | None = None) -> dict:
    """Operator trigger — deposit inbox subtopic + channel immediately."""
    from app.database.session import SessionLocal
    from app.services.aof_growth_hub import queue_storage_hub_deposits
    from app.services.intake_scheduler import get_batch_size, mark_lane_run
    from app.services.inbox_intake_review import flush_pending_inbox_quarantine
    from app.services.storage_topic_deposit import queue_inbox_channel_deposit

    lim = int(batch) if batch is not None else get_batch_size("inbox")
    with SessionLocal() as db:
        topic_report = queue_storage_hub_deposits(
            db,
            limit=lim,
            topic_keys=["inbox"],
            media_types="both",
            content_lanes_only=False,
            include_topic_mirror=False,
        )
        channel_report = queue_inbox_channel_deposit(db, limit=lim, media_types="both")
    mark_lane_run("inbox")
    flush = flush_pending_inbox_quarantine(force=True)
    try:
        flush_inbox_quarantine_albums.apply_async(countdown=120, kwargs={"force": True})
    except Exception:
        logger.debug("deferred inbox album flush enqueue failed", exc_info=True)
    return {
        "ok": True,
        "batch": lim,
        "topic": topic_report,
        "channel": channel_report,
        "inbox_flush": flush,
    }


@celery.task(name="app.workers.inbox_intake_worker.flush_inbox_quarantine_albums")
def flush_inbox_quarantine_albums(*, force: bool = True) -> dict:
    from app.services.inbox_intake_review import flush_pending_inbox_quarantine

    return flush_pending_inbox_quarantine(force=force)
