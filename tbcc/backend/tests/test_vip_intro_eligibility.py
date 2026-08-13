"""VIP intro month eligibility (first main-section subscription only)."""

from __future__ import annotations

from app.data.aof_vip_membership import VIP_INTRO_PLAN_NAME, VIP_INTRO_SKU
from app.models.subscription import Subscription  # noqa: F401 — register table
from app.models.subscription_plan import SubscriptionPlan
from app.services.vip_intro_eligibility import (
    assert_vip_intro_allowed,
    intro_purchase_error,
    user_eligible_for_vip_intro,
)


def test_user_eligible_when_no_main_subs(db) -> None:
    assert user_eligible_for_vip_intro(db, 999001) is True


def test_user_ineligible_after_main_sub(db) -> None:
    plan = SubscriptionPlan(
        name="AOF VIP — 1 Month",
        price_stars=1500,
        duration_days=30,
        is_active=True,
        product_type="subscription",
        bot_section="main",
    )
    db.add(plan)
    db.flush()
    db.add(
        Subscription(
            telegram_user_id=999002,
            plan_id=plan.id,
            plan=plan.name,
            status="expired",
            payment_method="stars",
            amount_stars=1500,
        )
    )
    db.commit()
    assert user_eligible_for_vip_intro(db, 999002) is False


def test_loot_sub_does_not_block_intro(db) -> None:
    plan = SubscriptionPlan(
        name="Loot Room 24h — 60min drops",
        price_stars=150,
        duration_days=1,
        is_active=True,
        product_type="subscription",
        bot_section="loot",
    )
    db.add(plan)
    db.flush()
    db.add(
        Subscription(
            telegram_user_id=999003,
            plan_id=plan.id,
            plan=plan.name,
            status="expired",
            payment_method="stars",
            amount_stars=150,
        )
    )
    db.commit()
    assert user_eligible_for_vip_intro(db, 999003) is True


def test_assert_intro_allowed_blocks_repeat(db) -> None:
    intro = SubscriptionPlan(
        name=VIP_INTRO_PLAN_NAME,
        price_stars=834,
        duration_days=30,
        is_active=True,
        product_type="subscription",
        bot_section="main",
    )
    vip = SubscriptionPlan(
        name="AOF VIP — 1 Month",
        price_stars=1500,
        duration_days=30,
        is_active=True,
        product_type="subscription",
        bot_section="main",
    )
    db.add_all([intro, vip])
    db.flush()
    db.add(
        Subscription(
            telegram_user_id=999004,
            plan_id=vip.id,
            plan=vip.name,
            status="active",
            payment_method="stars",
            amount_stars=1500,
        )
    )
    db.commit()
    assert assert_vip_intro_allowed(db, telegram_user_id=999004, plan=intro) == intro_purchase_error()
    assert assert_vip_intro_allowed(db, telegram_user_id=999005, plan=intro) is None
