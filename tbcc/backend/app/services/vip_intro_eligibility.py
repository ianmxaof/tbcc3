"""First-time VIP intro month — one purchase per Telegram user (main-section subs)."""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.data.aof_vip_membership import VIP_INTRO_PLAN_NAME, is_vip_intro_plan_name
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan


def vip_intro_usd() -> float:
    raw = (os.getenv("TBCC_VIP_INTRO_USD") or "10").strip()
    try:
        return max(1.0, min(15.0, float(raw)))
    except ValueError:
        return 10.0


def is_vip_intro_plan(plan: dict | SubscriptionPlan | None) -> bool:
    if not plan:
        return False
    if isinstance(plan, dict):
        return is_vip_intro_plan_name(str(plan.get("name") or ""))
    return is_vip_intro_plan_name(plan.name)


def user_eligible_for_vip_intro(db: Session, telegram_user_id: int) -> bool:
    """
    True when buyer has never held any main-section subscription (VIP or legacy main).
    Loot keys and pack bundles do not count.
    """
    uid = int(telegram_user_id)
    rows = (
        db.query(Subscription, SubscriptionPlan)
        .join(SubscriptionPlan, Subscription.plan_id == SubscriptionPlan.id)
        .filter(Subscription.telegram_user_id == uid)
        .all()
    )
    for _sub, plan in rows:
        if (plan.product_type or "subscription").lower() != "subscription":
            continue
        if (plan.bot_section or "main").strip().lower() != "main":
            continue
        return False
    return True


def intro_purchase_error() -> str:
    from app.data.aof_vip_membership import vip_display_name

    return f"This intro price is for first-time {vip_display_name()} buyers only. Use /subscribe for standard plans."


def assert_vip_intro_allowed(
    db: Session,
    *,
    telegram_user_id: int,
    plan: SubscriptionPlan | dict | None,
) -> str | None:
    """Return error message when intro purchase must be blocked; else None."""
    if not is_vip_intro_plan(plan):
        return None
    if user_eligible_for_vip_intro(db, int(telegram_user_id)):
        return None
    return intro_purchase_error()
