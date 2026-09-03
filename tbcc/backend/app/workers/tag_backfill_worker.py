"""Celery tasks: tag-only backfill re-enrich for already-approved media."""

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(
    name="app.workers.tag_backfill_worker.backfill_tag_media",
    soft_time_limit=45,
    time_limit=60,
)
def backfill_tag_media(media_id: int):
    from app.services.auto_tag_enrich import run_tag_backfill_for_media

    try:
        out = run_tag_backfill_for_media(media_id)
    except Exception as exc:
        name = type(exc).__name__
        if "SoftTimeLimit" in name or "TimeLimit" in name:
            logger.warning("backfill_tag_media media_id=%s timed_out: %s", media_id, exc)
            return {"ok": True, "media_id": media_id, "skipped": "soft_time_limit"}
        logger.warning("backfill_tag_media media_id=%s aborted: %s", media_id, exc)
        return {"ok": False, "media_id": media_id, "error": str(exc)}

    if not out.get("ok"):
        logger.warning("backfill_tag_media media_id=%s result=%s", media_id, out)
    return out


@celery.task(name="app.workers.tag_backfill_worker.tag_backfill_sweep_tick")
def tag_backfill_sweep_tick():
    from app.services.tag_backfill import run_tag_backfill_sweep

    out = run_tag_backfill_sweep()
    if out.get("queued"):
        logger.info("tag_backfill_sweep_tick result=%s", out)
    return out
