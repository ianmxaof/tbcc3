"""Shared active-subscription checks (VIP perks, loot daily roll, companion gate bypass)."""

from __future__ import annotations

from datetime import datetime

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
    return user_has_active_subscription(
        db,
        int(telegram_user_id),
        subscriptions_only=True,
        bot_section="main",
    )


def effective_link_resolver_tier(db: Session, telegram_user_id: int) -> str:
    """premium: any non-expired active subscription or bundle; free otherwise."""
    if _active_rows(db, int(telegram_user_id)):
        return "premium"
    return "free"
