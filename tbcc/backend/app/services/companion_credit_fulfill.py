"""Fulfill companion credit pack purchases from payment bot (Stars / crypto / Gumroad)."""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.data.companion_credit_packs import credit_units_for_plan_name, pack_for_plan_name
from app.models.subscription_plan import SubscriptionPlan

logger = logging.getLogger(__name__)

_GRANTED_PREFIX = "tbcc:companion:creditpack:"


def companion_credit_fulfill_enabled() -> bool:
    raw = (os.getenv("TBCC_COMPANION_CREDIT_PACKS_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def is_companion_credit_plan(plan: SubscriptionPlan | dict | None) -> bool:
    if plan is None:
        return False
    ptype = (
        (plan.product_type if hasattr(plan, "product_type") else plan.get("product_type"))
        or ""
    ).lower()
    if ptype != "companion_credits":
        return False
    name = plan.name if hasattr(plan, "name") else plan.get("name")
    return pack_for_plan_name(str(name or "")) is not None


def _redis():
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def _grant_key(charge_id: str) -> str:
    return f"{_GRANTED_PREFIX}{charge_id}"


def _already_granted(charge_id: str | None) -> bool:
    cid = (charge_id or "").strip()
    if not cid:
        return False
    r = _redis()
    if r is None:
        return False
    try:
        return bool(r.get(_grant_key(cid)))
    except Exception:
        return False


def _mark_granted(charge_id: str | None) -> None:
    cid = (charge_id or "").strip()
    if not cid:
        return
    r = _redis()
    if r is None:
        return
    try:
        r.setex(_grant_key(cid), 60 * 60 * 24 * 400, "1")
    except Exception:
        pass


def grant_companion_credit_pack(
    db: Session,
    telegram_user_id: int,
    plan_id: int,
    *,
    charge_id: str | None = None,
) -> dict[str, Any]:
    """
    Credit companion wallet after payment-bot purchase.
    Idempotent per telegram_payment_charge_id / external order id when Redis is available.
    """
    if not companion_credit_fulfill_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == int(plan_id)).first()
    if not plan:
        return {"ok": False, "error": "plan_not_found"}
    if not is_companion_credit_plan(plan):
        return {"ok": True, "skipped": True, "reason": "not_companion_credit_plan"}

    units = credit_units_for_plan_name(plan.name)
    if not units or units <= 0:
        return {"ok": False, "error": "unknown_credit_units"}

    if _already_granted(charge_id):
        return {
            "ok": True,
            "skipped": True,
            "reason": "already_granted",
            "charge_id": charge_id,
        }

    from app.services.companion_access import grant_credits

    uid = int(telegram_user_id)
    new_bal = grant_credits(uid, int(units))
    _mark_granted(charge_id)
    logger.info(
        "companion credit pack granted user=%s plan=%s units=%s balance=%s charge=%s",
        uid,
        plan_id,
        units,
        new_bal,
        charge_id,
    )
    return {
        "ok": True,
        "telegram_user_id": uid,
        "plan_id": int(plan_id),
        "credits_granted": int(units),
        "credits_balance": new_bal,
    }
