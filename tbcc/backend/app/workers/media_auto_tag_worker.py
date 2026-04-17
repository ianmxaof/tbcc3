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
