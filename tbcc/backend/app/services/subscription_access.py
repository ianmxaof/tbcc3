"""Shared active-subscription checks (VIP perks, loot daily roll, companion gate bypass)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan


def _active_rows(db: Session, telegram_user_id: int) -> list[Subscription]:
    now = datetime.utcnow()
    rows = (
        db.query(Subscription)
        .filter(
            Subscription.telegram_user_id == int(telegram_user_id),
            Subscription.status == "active",
        )
        .all()
    )
    out: list[Subscription] = []
    for sub in rows:
        exp = sub.expires_at
        if exp is None or exp > now:
            out.append(sub)
    return out


def user_has_active_subscription(
    db: Session,
    telegram_user_id: int,
    *,
    subscriptions_only: bool = True,
    bot_section: str | None = None,
) -> bool:
    """True when user has a non-expired active subscription row matching filters."""
    uid = int(telegram_user_id)
    for sub in _active_rows(db, uid):
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == sub.plan_id).first()
        if not plan:
            continue
        ptype = (plan.product_type or "subscription").lower()
        if subscriptions_only and ptype != "subscription":
            continue
        if bot_section is not None and (plan.bot_section or "main") != bot_section:
            continue
        return True
    return False


def is_aof_vip_subscriber(db: Session, telegram_user_id: int) -> bool:
    """Active main-section subscription (AOF VIP / group-access plan)."""
    from app.services.tbcc_operator_ids import is_tbcc_operator

    if is_tbcc_operator(telegram_user_id):
        return True
    return user_has_active_subscription(
        db,
        int(telegram_user_id),
        subscriptions_only=True,
        bot_section="main",
    )


def is_loot_key_holder(db: Session, telegram_user_id: int) -> bool:
    """Active loot-section subscription (24h Loot Room key / paid loot access)."""
    from app.services.tbcc_operator_ids import is_tbcc_operator

    if is_tbcc_operator(telegram_user_id):
        return True
    return user_has_active_subscription(
        db,
        int(telegram_user_id),
        subscriptions_only=True,
        bot_section="loot",
    )


def effective_link_resolver_tier(db: Session, telegram_user_id: int) -> str:
    """premium: any non-expired active subscription or bundle; free otherwise."""
    from app.services.tbcc_operator_ids import is_tbcc_operator

    if is_tbcc_operator(telegram_user_id):
        return "premium"
    if _active_rows(db, int(telegram_user_id)):
        return "premium"
    return "free"


def compensate_loot_key_card_failure(db: Session, telegram_user_id: int) -> dict:
    """
    When a paid key roll delivers loot but the tier card reveal fails, extend the
    active loot-section subscription by 24h so the user is not shorted on key time.
    """
    uid = int(telegram_user_id)
    now = datetime.utcnow()
    rows = (
        db.query(Subscription)
        .join(SubscriptionPlan, Subscription.plan_id == SubscriptionPlan.id)
        .filter(
            Subscription.telegram_user_id == uid,
            Subscription.status == "active",
            SubscriptionPlan.bot_section == "loot",
        )
        .all()
    )
    for sub in rows:
        exp = sub.expires_at
        if exp is not None and exp <= now:
            continue
        base = max(exp, now) if exp is not None else now
        sub.expires_at = base + timedelta(hours=24)
        db.commit()
        return {
            "ok": True,
            "subscription_id": int(sub.id),
            "extended_until": sub.expires_at.isoformat(),
        }
    return {"ok": False, "reason": "no_active_loot_subscription"}
