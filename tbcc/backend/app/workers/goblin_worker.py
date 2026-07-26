"""Celery tasks for loot goblin announce TTL."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.goblin_worker.goblin_announce_drop")
def goblin_announce_drop(drop_id: int):
    from app.database.session import SessionLocal
    from app.models.goblin_drop import GoblinDrop
    from app.models.listening_relay_settings import ListeningRelaySettings
    from app.services.goblin_announce import send_goblin_announce

    db = SessionLocal()
    try:
        drop = db.query(GoblinDrop).filter(GoblinDrop.id == int(drop_id)).first()
        if not drop:
            return {"ok": False, "error": "not_found"}
        settings = db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == 1).first()
        out = send_goblin_announce(db, drop, settings=settings)
        if not out.get("ok"):
            db.commit()
            return out
        ttl = int(out.get("ttl_seconds") or 45)
        db.commit()
        goblin_expire_announcement.apply_async(args=[int(drop_id)], countdown=max(5, ttl))
        return {"ok": True, "drop_id": int(drop_id), "message_id": out.get("message_id")}
    finally:
        db.close()


@celery.task(name="app.workers.goblin_worker.goblin_expire_announcement")
def goblin_expire_announcement(drop_id: int):
    from app.database.session import SessionLocal
    from app.models.goblin_drop import GoblinDrop
    from app.services.goblin_announce import delete_goblin_announce

    db = SessionLocal()
    try:
        drop = db.query(GoblinDrop).filter(GoblinDrop.id == int(drop_id)).first()
        if not drop:
            return {"ok": False, "error": "not_found"}
        out = delete_goblin_announce(db, drop)
        db.commit()
        return out
    finally:
        db.close()
