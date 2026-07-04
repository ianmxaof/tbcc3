"""Celery: mirror MEGA pack destinations to Keep2Share after pool resolve."""

from __future__ import annotations

import logging

from app.database.session import SessionLocal
from app.services.k2s_mirror_service import mirror_modifier_by_id
from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.k2s_mirror_worker.mirror_pack_to_k2s", bind=True, max_retries=2)
def mirror_pack_to_k2s(self, modifier_id: int, lane: str = "packs") -> dict:
    db = SessionLocal()
    try:
        result = mirror_modifier_by_id(db, int(modifier_id), lane=(lane or "packs"))
        if not result.get("ok") and result.get("error") == "mirror_failed":
            raise self.retry(countdown=120)
        return result
    except Exception as e:
        logger.exception("k2s mirror task failed mod=%s: %s", modifier_id, e)
        raise
    finally:
        db.close()
