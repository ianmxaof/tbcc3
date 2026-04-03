"""Periodic promotional bulletin to AOF landing chat (group or forum topic)."""
import logging
import os

import httpx

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.landing_bulletin_worker.send_aof_landing_bulletin")
def send_aof_landing_bulletin(force: bool = False):
    """
    Post growth/referral/milestone copy to Telegram.

    Chat id + hour: dashboard /growth-settings (DB) or TBCC_LANDING_* env.
    Beat runs hourly; only the configured UTC hour sends — unless force=True (manual test).
    """
    from datetime import datetime, timezone

    from app.database.session import SessionLocal
    from app.services.growth_promo import build_aof_landing_bulletin_text
    from app.services.growth_settings_effective import get_effective_growth_settings

    db = SessionLocal()
    try:
        s = get_effective_growth_settings(db)
        target_hour = int(s.get("landing_bulletin_hour_utc", 14))
        now_h = datetime.now(timezone.utc).hour
        if not force and now_h != target_hour:
            logger.info(
                "Landing bulletin skipped: UTC hour %s != configured %s "
                "(match Send hour UTC in Growth, or: celery call ... --kwargs '{\"force\": true}')",
                now_h,
                target_hour,
            )
            return

        chat_id = (s.get("landing_bulletin_chat_id") or "").strip()
        if not chat_id:
            logger.debug("Landing bulletin: no chat id (dashboard or TBCC_LANDING_BULLETIN_CHAT_ID)")
            return

        text = build_aof_landing_bulletin_text(db)
        tid = s.get("landing_bulletin_message_thread_id")
    finally:
        db.close()

    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        logger.warning("BOT_TOKEN unset — skip landing bulletin")
        return

    payload: dict = {"chat_id": chat_id, "text": text}
    if isinstance(tid, int) and tid > 0:
        payload["message_thread_id"] = tid

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with httpx.Client(timeout=15) as client:
            r = client.post(url, json=payload)
            if r.status_code != 200:
                logger.warning("Landing bulletin failed: %s %s", r.status_code, r.text)
            else:
                logger.info("Landing bulletin sent to chat_id=%s", chat_id)
    except Exception as e:
        logger.exception("Landing bulletin error: %s", e)
