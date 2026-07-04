"""Grant recurring VIP perks on subscription fulfillment (companion credits, gate bypass)."""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.models.subscription_plan import SubscriptionPlan
from app.services.aof_growth_hub import resolve_group_access_plan_id

logger = logging.getLogger(__name__)

_PERKS_GRANTED_PREFIX = "tbcc:vip:perks:"


def vip_perks_enabled() -> bool:
    raw = (os.getenv("TBCC_VIP_PERKS_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def vip_companion_bonus_credits() -> int:
    raw = (os.getenv("TBCC_VIP_COMPANION_BONUS_CREDITS") or "3").strip()
    try:
        return max(0, min(20, int(raw)))
    except ValueError:
        return 3


def vip_companion_skip_gate() -> bool:
    raw = (os.getenv("TBCC_VIP_COMPANION_SKIP_GATE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def is_group_access_plan(db: Session, plan_id: int) -> bool:
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == int(plan_id)).first()
    if not plan or plan.is_active is False:
        return False
    if (plan.product_type or "subscription").lower() != "subscription":
        return False
    return (plan.bot_section or "main") == "main"


def _redis():
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def _perks_key(charge_id: str) -> str:
    return f"{_PERKS_GRANTED_PREFIX}{charge_id}"


def _already_granted(charge_id: str | None) -> bool:
    cid = (charge_id or "").strip()
    if not cid:
        return False
    r = _redis()
    if r is None:
        return False
    try:
        return bool(r.get(_perks_key(cid)))
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
        r.setex(_perks_key(cid), 60 * 60 * 24 * 400, "1")
    except Exception:
        pass


def grant_vip_subscription_perks(
    db: Session,
    telegram_user_id: int,
    plan_id: int,
    *,
    charge_id: str | None = None,
) -> dict[str, Any]:
    """
    On new main-section subscription: companion bonus credits + gate bypass flag.
    Idempotent per telegram_payment_charge_id when Redis is available.
    """
    if not vip_perks_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}
    if not is_group_access_plan(db, int(plan_id)):
        return {"ok": True, "skipped": True, "reason": "not_group_access_plan"}
    if _already_granted(charge_id):
        return {"ok": True, "skipped": True, "reason": "already_granted", "charge_id": charge_id}

    uid = int(telegram_user_id)
    bonus = vip_companion_bonus_credits()
    result: dict[str, Any] = {"ok": True, "telegram_user_id": uid, "plan_id": int(plan_id)}

    if bonus > 0:
        from app.services.companion_access import grant_credits, get_access, save_access

        new_bal = grant_credits(uid, bonus)
        acc = get_access(uid)
        acc.vip_subscriber = True
        save_access(acc)
        result["companion_credits_granted"] = bonus
        result["companion_credits_balance"] = new_bal
    elif vip_companion_skip_gate():
        from app.services.companion_access import get_access, save_access

        acc = get_access(uid)
        acc.vip_subscriber = True
        save_access(acc)

    _mark_granted(charge_id)
    logger.info("vip perks granted user=%s plan=%s bonus=%s charge=%s", uid, plan_id, bonus, charge_id)
    return result


def default_group_access_plan_id(db: Session) -> int:
    return resolve_group_access_plan_id(db)
