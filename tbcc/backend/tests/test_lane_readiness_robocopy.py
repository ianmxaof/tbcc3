"""Tests for lane readiness audit + robocopy watermark tier configs."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.data.loot_lane_economy import (
    LANE_PASS_SKU,
    MONTHLY_MEGA,
    PACK_DROP,
    WatermarkTier,
    usd_to_stars,
)
from app.services.robocopy_watermark import apply_config_for_tier


def test_sku_prices_locked() -> None:
    assert LANE_PASS_SKU.price_usd == 3.0
    assert PACK_DROP.price_usd == 12.0
    assert MONTHLY_MEGA.price_usd == 25.0
    assert PACK_DROP.sku_name == "Curated Pack"
    assert MONTHLY_MEGA.sku_name == "Monthly MEGA PACK"
    assert usd_to_stars(3.0, stars_per_usd=0.012) == 250
    assert usd_to_stars(12.0, stars_per_usd=0.012) == 1000


def test_robocopy_tier_configs() -> None:
    promo = apply_config_for_tier(WatermarkTier.PROMO_HEAVY)
    lane = apply_config_for_tier(WatermarkTier.LANE_LIGHT)
    vault = apply_config_for_tier(WatermarkTier.VAULT_CLEAN)
    assert promo.skip is False and promo.opacity >= 0.65
    assert len(promo.texts) >= 2
    assert lane.skip is False and lane.opacity < promo.opacity
    assert vault.skip is True or vault.enabled is False


def test_audit_lane_readiness_shape() -> None:
    from app.services.lane_readiness import audit_lane_readiness

    db = MagicMock()
    # No pools found → all zeros
    db.query.return_value.filter.return_value.first.return_value = None
    report = audit_lane_readiness(db)
    assert report["ok"] is True
    assert report["lanes_eligible"] >= 8
    assert "thresholds" in report
    assert report["lanes_ready_for_subtopic"] == 0
    keys = {r["network_key"] for r in report["lanes"]}
    assert "milf" in keys
    assert "big_tits" in keys
    assert "main" not in keys
