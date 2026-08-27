"""Celery task: LLM vision auto-tag for media rows."""

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.media_auto_tag_worker.auto_tag_media_llm")
def auto_tag_media_llm(media_id: int):
    from app.services.auto_tag_llm import run_auto_tag_llm_for_media

    out = run_auto_tag_llm_for_media(media_id)
    if not out.get("ok"):
        logger.warning("auto_tag_media_llm media_id=%s result=%s", media_id, out)
    else:
        logger.info("auto_tag_media_llm media_id=%s result=%s", media_id, out)
    return out


def _loggable(out: dict) -> dict:
    """Drop the 512-float CLIP embedding — the gatekeeper needs it, the log does not."""
    embedding = out.get("clip_embedding")
    if not isinstance(embedding, list):
        return out
    return {**out, "clip_embedding": f"<{len(embedding)} floats>"}


@celery.task(
    name="app.workers.media_auto_tag_worker.auto_tag_media_enrich",
    soft_time_limit=120,
    time_limit=150,
)
def auto_tag_media_enrich(media_id: int):
    """Classify one media. Soft-killed at 120s so a hung Telethon download cannot
    starve Inbox now / deposit on the solo telegram worker.
    """
    from app.services.auto_tag_enrich import run_auto_tag_enrich_for_media

    try:
        out = run_auto_tag_enrich_for_media(media_id)
    except Exception as exc:
        # Celery SoftTimeLimitExceeded subclasses Exception
        logger.warning("auto_tag_media_enrich media_id=%s aborted: %s", media_id, exc)
        return {"ok": False, "media_id": media_id, "error": str(exc), "aborted": True}

    if not out.get("ok"):
        logger.warning("auto_tag_media_enrich media_id=%s result=%s", media_id, _loggable(out))
    else:
        logger.info("auto_tag_media_enrich media_id=%s result=%s", media_id, _loggable(out))
    return out


@celery.task(name="app.workers.media_auto_tag_worker.auto_tag_enrich_backlog_tick")
def auto_tag_enrich_backlog_tick():
    from app.services.enrich_backlog import run_enrich_backlog_sweep

    out = run_enrich_backlog_sweep()
    if out.get("queued"):
        logger.info("auto_tag_enrich_backlog_tick result=%s", out)
    return out
