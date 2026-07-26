"""Celery: post quarantine review cards to Telegram."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.gatekeeper_review_worker.send_quarantine_review")
def send_quarantine_review_task(media_id: int) -> dict:
    from app.database.session import SessionLocal
    from app.services.gatekeeper_review import send_quarantine_review_message

    with SessionLocal() as db:
        out = send_quarantine_review_message(db, int(media_id))
    if not out.get("ok"):
        logger.info("quarantine review skip media_id=%s %s", media_id, out)
    return out
