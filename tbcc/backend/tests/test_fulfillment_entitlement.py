"""Fulfillment entitlement wiring."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.buyer_entitlement import BuyerEntitlement
from app.models.subscription_plan import SubscriptionPlan
from app.services.fulfillment_entitlement import record_fulfillment_entitlement


def _session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        eng,
        tables=[BuyerEntitlement.__table__, SubscriptionPlan.__table__],
    )
    return sessionmaker(bind=eng)()


def test_vip_entitlement_on_fulfillment() -> None:
    db = _session()
    plan = SubscriptionPlan(
        id=10,
        name="AOF VIP — 1 Month",
        price_stars=1500,
        duration_days=30,
        product_type="subscription",
        bot_section="main",
        is_active=True,
    )
    db.add(plan)
    db.commit()

    out = record_fulfillment_entitlement(
        db,
        telegram_user_id=999,
        plan=plan,
        subscription_id=1,
        invite_url="https://t.me/+vip",
        payment_method="gumroad",
    )
    assert out is not None
    assert out["kind"] == "vip"
    rows = db.query(BuyerEntitlement).filter(BuyerEntitlement.telegram_user_id == 999).all()
    assert len(rows) == 1
    assert rows[0].kind == "vip"
    assert rows[0].plan_id == 10


def test_curated_pack_entitlement_open_ended() -> None:
    db = _session()
    plan = SubscriptionPlan(
        id=20,
        name="Curated Pack",
        price_stars=1000,
        duration_days=0,
        product_type="bundle",
        bot_section="packs",
        is_active=True,
    )
    db.add(plan)
    db.commit()

    out = record_fulfillment_entitlement(
        db,
        telegram_user_id=888,
        plan=plan,
        subscription_id=2,
        payment_method="stars",
    )
    assert out is not None
    assert out["kind"] == "curated_pack"
    row = db.query(BuyerEntitlement).filter(BuyerEntitlement.telegram_user_id == 888).one()
    assert row.ends_at is None
