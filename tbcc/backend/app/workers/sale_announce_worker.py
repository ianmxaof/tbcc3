"""Celery task: anonymous public sale announce (Telegram network + Buffer X)."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.sale_announce_worker.announce_public_sale")
def announce_public_sale(sale_kind: str, plan_name: str = "", payment_method: str = "") -> dict:
    from app.database.session import SessionLocal
    from app.services.sale_public_announce import run_public_sale_announce

    db = SessionLocal()
    try:
        result = run_public_sale_announce(
            db,
            sale_kind=str(sale_kind or "subscription"),
            plan_name=str(plan_name or "") or None,
            payment_method=str(payment_method or "") or None,
        )
        logger.info(
            "sale announce kind=%s ok=%s skipped=%s",
            sale_kind,
            result.get("ok"),
            result.get("skipped") or result.get("reason"),
        )
        return result
    except Exception:
        logger.exception("announce_public_sale failed kind=%s", sale_kind)
        raise
    finally:
        db.close()
