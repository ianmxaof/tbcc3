"""Stars bait copy + outreach tests."""

from app.database.session import SessionLocal, engine
from app.models.base import Base
from app.models.funnel_strategy import FunnelStrategyEntry
from app.models.subscription_plan import SubscriptionPlan
from app.services.funnel_rag import seed_stars_bait_funnel_strategies
from app.services.stars_bait_copy import (
    StarsBaitProduct,
    StarsBaitStyle,
    all_stars_bait_variations,
    bait_handoff_payload,
    parse_bait_start_payload,
    stars_bait_inline_keyboard,
)


def test_all_variations_cover_products_and_styles():
    vars_ = all_stars_bait_variations({"loot_key": 1, "day_pass": 2, "subscription": 10})
    assert len(vars_) == 15
    products = {v.product for v in vars_}
    styles = {v.style for v in vars_}
    assert products == set(StarsBaitProduct)
    assert styles == set(StarsBaitStyle)


def test_bait_handoff_payloads():
    assert bait_handoff_payload(StarsBaitProduct.LOOT_KEY) == "bait_loot"
    assert bait_handoff_payload(StarsBaitProduct.DAY_PASS) == "bait_day"
    assert bait_handoff_payload(StarsBaitProduct.SUBSCRIPTION) == "bait_vip"


def test_parse_bait_start_payload():
    assert parse_bait_start_payload("bait_loot") == StarsBaitProduct.LOOT_KEY
    assert parse_bait_start_payload("bait_vip") == StarsBaitProduct.SUBSCRIPTION
    assert parse_bait_start_payload("cm10") is None


def test_inline_keyboard_has_button_url():
    v = all_stars_bait_variations()[0]
    kb = stars_bait_inline_keyboard(v)
    assert "inline_keyboard" in kb
    assert kb["inline_keyboard"][0][0]["url"].startswith("https://t.me/")


def test_seed_stars_bait_funnel_strategies_idempotent():
    Base.metadata.create_all(engine, tables=[FunnelStrategyEntry.__table__])
    db = SessionLocal()
    try:
        n1 = seed_stars_bait_funnel_strategies(db)
        n2 = seed_stars_bait_funnel_strategies(db)
        assert n1 >= 5
        assert n2 == 0
        row = (
            db.query(FunnelStrategyEntry)
            .filter(FunnelStrategyEntry.pattern == "stars_dm_welcome_trap")
            .first()
        )
        assert row is not None
        assert "arturmoreirazerozerobot" in (row.copy_template or "")
    finally:
        db.close()
