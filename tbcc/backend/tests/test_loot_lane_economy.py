"""Scaffold tests for Loot Room lane economy product constants."""

from __future__ import annotations

from app.data.aof_network import AOF_NETWORK_CHANNELS
from app.data.loot_lane_economy import (
    CHANNEL_READINESS,
    FORWARD_WINDOW,
    GLIMPSE,
    LANE_PASS,
    LANE_TOPIC_ELIGIBLE_KEYS,
    MONTHLY_MEGA,
    PACK_DROP,
    RECOVERY,
    WatermarkTier,
    lane_at_target_median,
    lane_display_name,
    lane_ready_for_loot_subtopic,
    pack_item_count_in_soft_band,
)


def test_lane_pass_is_three_dollars_protected() -> None:
    assert LANE_PASS.price_usd == 3.0
    assert LANE_PASS.duration_hours == 24
    assert LANE_PASS.one_use is True
    assert LANE_PASS.content_protected is True
    assert LANE_PASS.watermark == WatermarkTier.LANE_LIGHT
    assert FORWARD_WINDOW.clean_forwards is False


def test_glimpse_left_visible_heavy_watermark() -> None:
    assert GLIMPSE.leave_visible is True
    assert GLIMPSE.watermark == WatermarkTier.PROMO_HEAVY
    assert GLIMPSE.shown_of_full == (1, 7)
    assert GLIMPSE.forwards_enabled is False


def test_pack_and_mega_specs() -> None:
    assert PACK_DROP.curation_required is True
    assert PACK_DROP.soft_min_items == 250
    assert PACK_DROP.soft_max_items == 400
    assert PACK_DROP.price_usd == 12.0
    assert pack_item_count_in_soft_band(300) is True
    assert pack_item_count_in_soft_band(100) is False
    assert MONTHLY_MEGA.wraps_curated_packs is True
    assert MONTHLY_MEGA.cadence == "monthly"
    assert MONTHLY_MEGA.price_usd == 25.0


def test_channel_readiness_thresholds() -> None:
    assert CHANNEL_READINESS.min_images == 2_500
    assert CHANNEL_READINESS.min_videos == 2_500
    assert CHANNEL_READINESS.target_median_images == 5_000
    assert CHANNEL_READINESS.aspirational_per_format == 10_000
    assert lane_ready_for_loot_subtopic(images=2_500, videos=2_500) is True
    assert lane_ready_for_loot_subtopic(images=2_499, videos=10_000) is False
    assert lane_at_target_median(images=5_000, videos=5_000) is True
    assert lane_at_target_median(images=4_999, videos=9_000) is False


def test_recovery_rejects_fake_tactics() -> None:
    assert RECOVERY.entitlement_ledger is True
    assert RECOVERY.seed_backup_channels is True
    assert RECOVERY.fake_abuse_banners is False
    assert RECOVERY.share_or_get_banned is False
    assert RECOVERY.positive_invite_for_roll is True


def test_every_eligible_lane_has_display_label() -> None:
    assert "main" not in LANE_TOPIC_ELIGIBLE_KEYS
    assert "packs" not in LANE_TOPIC_ELIGIBLE_KEYS
    for key in LANE_TOPIC_ELIGIBLE_KEYS:
        name = lane_display_name(key)
        assert name
        assert name != key or any(ch.key == key for ch in AOF_NETWORK_CHANNELS)
    # Known vertical still labeled
    assert "MILF" in lane_display_name("milf").upper() or "milf" in lane_display_name("milf").lower()
    assert lane_display_name("big_tits")
