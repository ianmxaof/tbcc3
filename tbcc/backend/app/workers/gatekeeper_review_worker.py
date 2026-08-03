"""Celery: post quarantine review cards to Telegram."""

from __future__ import annotations

import asyncio
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


@celery.task(name="app.workers.gatekeeper_review_worker.bulk_approve_waiting")
def bulk_approve_waiting_task(operator_id: int, lane_key: str = "") -> dict:
    from app.database.session import SessionLocal
    from app.services.gatekeeper_review import operator_approve_all_waiting

    op = int(operator_id) if operator_id else None
    lane = (lane_key or "").strip().lower() or None
    with SessionLocal() as db:
        out = operator_approve_all_waiting(db, operator_id=op, lane_key=lane)
    logger.info(
        "gatekeeper bulk approve operator=%s lane=%s approved=%s skipped=%s total=%s",
        op,
        lane,
        out.get("approved"),
        out.get("skipped"),
        out.get("total"),
    )
    return out


@celery.task(name="app.workers.gatekeeper_review_worker.route_approved_lanes")
def route_approved_lanes_task(media_id: int, lane_keys: list[str]) -> dict:
    from app.database.session import SessionLocal
    from app.models.media import Media
    from app.services.gatekeeper_lane_route import route_media_to_lane_topics
    from app.services.telegram_admin import run_telegram_io

    lanes = sorted({(x or "").strip().lower() for x in (lane_keys or []) if (x or "").strip()})
    if not lanes:
        return {"ok": False, "reason": "no_lanes", "media_id": media_id}

    with SessionLocal() as db:
        media = db.query(Media).filter(Media.id == int(media_id)).first()
        if not media:
            return {"ok": False, "reason": "not_found", "media_id": media_id}

    async def _run(storage):
        return await route_media_to_lane_topics(storage, media, lanes)

    try:
        out = asyncio.run(run_telegram_io(_run))
    except Exception as e:
        logger.exception("route_approved_lanes failed media_id=%s", media_id)
        return {"ok": False, "media_id": media_id, "error": str(e)[:400]}

    return {"ok": True, "media_id": media_id, **out}


@celery.task(name="app.workers.gatekeeper_review_worker.vault_approved_media")
def vault_approved_media_task(media_id: int) -> dict:
    from app.database.session import SessionLocal
    from app.services.gatekeeper_review import maybe_vault_and_evict_approved_media

    with SessionLocal() as db:
        out = maybe_vault_and_evict_approved_media(db, int(media_id))
    return out if isinstance(out, dict) else {"ok": False, "media_id": media_id}
