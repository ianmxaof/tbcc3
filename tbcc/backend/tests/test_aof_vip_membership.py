"""AOF VIP membership ladder constants (Gumroad ynnulc mirror)."""

from __future__ import annotations

from app.data.aof_vip_membership import (
    VIP_MEMBERSHIP_SKUS,
    VIP_PRICE_CENTS_TO_RECURRENCE,
    sku_for_duration_days,
    sku_for_price_cents,
    sku_for_recurrence,
)
from app.data.loot_lane_economy import usd_to_stars
from app.services.gumroad_ping import (
    append_tbcc_ref,
    append_vip_checkout_hints,
    recurrence_for_plan,
    resolve_plan_id_from_payload,
)


def test_vip_ladder_matches_gumroad_ynnulc() -> None:
    assert len(VIP_MEMBERSHIP_SKUS) == 5
    by_rec = {s.gumroad_recurrence: s for s in VIP_MEMBERSHIP_SKUS}
    assert by_rec["monthly"].price_usd == 18.0
    assert by_rec["quarterly"].price_usd == 48.0
    assert by_rec["biannually"].price_usd == 90.0
    assert by_rec["yearly"].price_usd == 168.0
    assert by_rec["every_two_years"].price_usd == 300.0
    assert by_rec["monthly"].duration_days == 30
    assert by_rec["every_two_years"].duration_days == 730


def test_vip_stars_at_default_rate() -> None:
    assert usd_to_stars(18.0, stars_per_usd=0.012) == 1500
    assert usd_to_stars(48.0, stars_per_usd=0.012) == 4000
    assert usd_to_stars(90.0, stars_per_usd=0.012) == 7500
    assert usd_to_stars(168.0, stars_per_usd=0.012) == 14000
    assert usd_to_stars(300.0, stars_per_usd=0.012) == 25000


def test_sku_lookups() -> None:
    assert sku_for_recurrence("yearly") is not None
    assert sku_for_duration_days(90).price_usd == 48.0
    assert sku_for_price_cents(5400).gumroad_recurrence == "yearly"
    assert sku_for_price_cents(1800).gumroad_recurrence == "monthly"
    assert sku_for_price_cents(600).gumroad_recurrence == "monthly"  # legacy grandfather
    legacy = {600, 1500, 3000, 5400, 10000}
    current = {1800, 4800, 9000, 16800, 30000}
    assert set(VIP_PRICE_CENTS_TO_RECURRENCE) == legacy | current


def test_append_vip_checkout_hints() -> None:
    url = append_tbcc_ref("https://aof69.gumroad.com/l/ynnulc", "EPO-AABBCCDDEEFF")
    url = append_vip_checkout_hints(url, recurrence="quarterly", option_name="Tiers")
    assert "tbcc_ref=EPO-AABBCCDDEEFF" in url
    assert "recurrence=quarterly" in url
    assert "option=Tiers" in url


def test_recurrence_for_plan() -> None:
    assert recurrence_for_plan({"duration_days": 180}) == "biannually"
    assert recurrence_for_plan({"nowpayments_price_usd": 168}) == "yearly"


def test_resolve_plan_id_price_cents(monkeypatch) -> None:
    monkeypatch.setenv(
        "TBCC_GUMROAD_PRODUCT_MAP",
        '{"ynnulc": 10, "price:1500": 11, "price:5400": 12}',
    )
    # price:* wins over permalink for multi-term VIP
    assert resolve_plan_id_from_payload({"permalink": "ynnulc", "price": "1500"}) == 11
    assert resolve_plan_id_from_payload({"price": "5400"}) == 12
    assert resolve_plan_id_from_payload({"permalink": "ynnulc"}) == 10
