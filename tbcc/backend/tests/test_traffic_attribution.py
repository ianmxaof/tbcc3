"""Traffic attribution — payload mapping and touch recording."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.models.growth_attribution_event import GrowthAttributionEvent
from app.models.user_funnel_touch import UserFunnelTouch
from app.services.growth_attribution import EVENT_SUBSCRIPTION_CREATED
from app.services.traffic_attribution import (
    conversions_by_source,
    payload_to_source_ref,
    record_traffic_touch,
    resolve_attribution_for_user,
    touch_for_conversion,
)


def test_payload_to_source_ref_bait_and_loot():
    assert payload_to_source_ref("bait_loot") == "src_bait_loot"
    assert payload_to_source_ref("bait_vip") == "src_bait_vip"
    assert payload_to_source_ref("loot_free") == "src_loot_free"
    assert payload_to_source_ref("loot") == "src_loot_paid"
    assert payload_to_source_ref("goblin_abc123") == "src_goblin_claim"
    assert payload_to_source_ref("ref_999") == "src_ref_user_999"
    assert payload_to_source_ref("cm10") == "src_checkout_plan_10"
    assert payload_to_source_ref("src_lv_loot_wk30") == "src_lv_loot_wk30"
    assert payload_to_source_ref("src_spicy_x") == "src_spicy_x"
    assert payload_to_source_ref("spicy_x") == "src_spicy_x"
    assert payload_to_source_ref("spicy_goblin") == "src_spicy_goblin"
    assert payload_to_source_ref("spicy") == "src_spicy"
    assert payload_to_source_ref("") is None
    assert payload_to_source_ref("vf_username") is None


def test_record_traffic_touch_first_and_last():
    db = MagicMock()
    row = UserFunnelTouch(
        telegram_user_id=42,
        first_source_ref="src_bait_loot",
        first_entry_payload="bait_loot",
        first_seen_at=datetime.utcnow() - timedelta(days=1),
        last_source_ref="src_bait_loot",
        last_entry_payload="bait_loot",
        last_seen_at=datetime.utcnow() - timedelta(days=1),
        touch_count=1,
    )
    db.query.return_value.filter.return_value.first.return_value = row

    out = record_traffic_touch(db, 42, "bait_vip", commit=False)
    assert out["ok"] is True
    assert row.last_source_ref == "src_bait_vip"
    assert row.touch_count == 2
    assert row.first_source_ref == "src_bait_loot"


def test_resolve_attribution_for_user_first_touch(monkeypatch):
    monkeypatch.setenv("TBCC_ATTRIBUTION_TOUCH_MODEL", "first")
    db = MagicMock()
    row = UserFunnelTouch(
        telegram_user_id=7,
        first_source_ref="src_loot_free",
        first_entry_payload="loot_free",
        first_seen_at=datetime.utcnow(),
        last_source_ref="src_bait_vip",
        last_entry_payload="bait_vip",
        last_seen_at=datetime.utcnow(),
        touch_count=2,
    )
    db.query.return_value.filter.return_value.first.return_value = row

    attr = resolve_attribution_for_user(db, 7)
    assert attr["traffic_source_ref"] == "src_loot_free"
    assert attr["traffic_entry_payload"] == "loot_free"


def test_touch_for_conversion_expired(monkeypatch):
    monkeypatch.setenv("TBCC_ATTRIBUTION_TOUCH_TTL_DAYS", "7")
    db = MagicMock()
    row = UserFunnelTouch(
        telegram_user_id=1,
        first_source_ref="src_bait_loot",
        first_entry_payload="bait_loot",
        first_seen_at=datetime.utcnow() - timedelta(days=30),
        last_source_ref="src_bait_loot",
        last_entry_payload="bait_loot",
        last_seen_at=datetime.utcnow() - timedelta(days=30),
        touch_count=1,
    )
    db.query.return_value.filter.return_value.first.return_value = row
    assert touch_for_conversion(db, 1) is None


def test_conversions_by_source_groups_events():
    db = MagicMock()
    recent_loot = GrowthAttributionEvent(
        event_type=EVENT_SUBSCRIPTION_CREATED,
        created_at=datetime.utcnow(),
        amount_stars=500,
        traffic_source_ref="src_bait_loot",
    )
    recent_vip = GrowthAttributionEvent(
        event_type=EVENT_SUBSCRIPTION_CREATED,
        created_at=datetime.utcnow(),
        amount_stars=500,
        traffic_source_ref="src_bait_vip",
    )
    unattributed = GrowthAttributionEvent(
        event_type=EVENT_SUBSCRIPTION_CREATED,
        created_at=datetime.utcnow(),
        amount_stars=150,
        traffic_source_ref=None,
    )
    db.query.return_value.filter.return_value.all.return_value = [
        recent_loot,
        recent_vip,
        unattributed,
    ]

    out = conversions_by_source(db, days=30)
    assert out["unattributed_subscriptions"] == 1
    assert len(out["conversions_by_source"]) == 2
    assert out["conversions_by_source"][0]["stars"] == 500
