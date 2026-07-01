"""Send AOF VIP welcome DM after subscription fulfillment (crypto, manual, API paths)."""

from __future__ import annotations

import logging
import os

import httpx

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)

_WELCOME_DM_PREFIX = "tbcc:vip:welcome_dm:"


def welcome_dm_from_worker_enabled() -> bool:
    raw = (os.getenv("TBCC_VIP_WELCOME_DM_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def should_autodm_from_worker(payment_method: str | None) -> bool:
    """
    Stars checkout replies in the payment-bot chat (instant).
    Native VIP channel joins get a DM from aof_vip_member_sync.
    Worker covers crypto, manual mark-paid, webhooks, etc.
    """
    pm = (payment_method or "").strip().lower()
    return pm not in ("stars", "vip_star_subscription")


def _redis():
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def _welcome_dm_key(*, telegram_user_id: int, plan_id: int, charge_id: str | None) -> str:
    cid = (charge_id or "").strip()
    if cid:
        return f"{_WELCOME_DM_PREFIX}{cid}"
    return f"{_WELCOME_DM_PREFIX}{int(telegram_user_id)}:{int(plan_id)}"


def _already_sent(key: str) -> bool:
    r = _redis()
    if r is None:
        return False
    try:
        return bool(r.get(key))
    except Exception:
        return False


def _mark_sent(key: str) -> None:
    r = _redis()
    if r is None:
        return
    try:
        r.setex(key, 60 * 60 * 24 * 400, "1")
    except Exception:
        pass


def send_vip_welcome_dm_sync(
    telegram_user_id: int,
    plan_id: int,
    *,
    charge_id: str | None = None,
    payment_method: str | None = None,
) -> dict:
    """Bot API DM with VIP invite — idempotent per charge_id when Redis available."""
    from app.database.session import SessionLocal
    from app.models.subscription_plan import SubscriptionPlan
    from app.services.aof_vip_fulfillment import fulfillment_invite_link, vip_welcome_message_html
    from app.services.aof_vip_perks import is_group_access_plan

    if not welcome_dm_from_worker_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    if payment_method is not None and not should_autodm_from_worker(payment_method):
        return {"ok": True, "skipped": True, "reason": "handled_elsewhere", "payment_method": payment_method}

    key = _welcome_dm_key(telegram_user_id=telegram_user_id, plan_id=plan_id, charge_id=charge_id)
    if _already_sent(key):
        return {"ok": True, "skipped": True, "reason": "already_sent", "key": key}

    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        return {"ok": False, "error": "BOT_TOKEN_missing"}

    db = SessionLocal()
    try:
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == int(plan_id)).first()
        if not plan:
            return {"ok": False, "error": "plan_not_found"}
        if (plan.product_type or "").lower() == "bundle":
            return {"ok": True, "skipped": True, "reason": "bundle"}
        if not is_group_access_plan(db, int(plan_id)):
            return {"ok": True, "skipped": True, "reason": "not_group_access"}

        invite = fulfillment_invite_link(db, plan)
        text = vip_welcome_message_html(invite_link=invite)
    finally:
        db.close()

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with httpx.Client(timeout=15) as client:
            r = client.post(
                url,
                json={
                    "chat_id": int(telegram_user_id),
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                },
            )
        if r.status_code != 200:
            logger.warning("vip welcome dm failed user=%s: %s", telegram_user_id, r.text[:300])
            return {"ok": False, "error": "telegram_api", "status": r.status_code, "body": r.text[:200]}
    except Exception as e:
        logger.warning("vip welcome dm failed user=%s: %s", telegram_user_id, e)
        return {"ok": False, "error": str(e)[:200]}

    _mark_sent(key)
    logger.info("vip welcome dm sent user=%s plan=%s", telegram_user_id, plan_id)
    return {"ok": True, "sent": True, "telegram_user_id": telegram_user_id, "plan_id": plan_id}


@celery.task(name="app.workers.vip_welcome_worker.send_subscription_welcome_dm")
def send_subscription_welcome_dm(
    telegram_user_id: int,
    plan_id: int,
    charge_id: str | None = None,
    payment_method: str | None = None,
):
    return send_vip_welcome_dm_sync(
        int(telegram_user_id),
        int(plan_id),
        charge_id=charge_id,
        payment_method=payment_method,
    )
