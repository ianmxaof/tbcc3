"""Shared-library loot eligibility: every named pool → tiers 1–10."""

from __future__ import annotations

from app.services.loot_pool_eligibility_seed import tier_band_for_pool_name
from app.services.loot_roll_preview import _pools_for_tier


class _Row:
    def __init__(self, pid: int, *, enabled: bool = True, lo: int = 7, hi: int = 10):
        self.content_pool_id = pid
        self.loot_enabled = enabled
        self.min_rarity_tier = lo
        self.max_rarity_tier = hi


def test_tier_band_full_ladder_for_any_named_pool():
    for name in (
        "AOF AI POOL",
        "AOF VIP POOL",
        "AOF FULL LENGTH",
        "LOOT ROOM VAULT",
        "PACKS PROMO",
        "RANDOM HUB",
    ):
        assert tier_band_for_pool_name(name) == (1, 10)
    assert tier_band_for_pool_name("") is None
    assert tier_band_for_pool_name("   ") is None


def test_pools_for_tier_uses_all_enabled_ignoring_narrow_bands():
    rows = [
        _Row(1, lo=1, hi=5),
        _Row(2, lo=7, hi=10),
        _Row(3, enabled=False, lo=1, hi=10),
    ]
    got = _pools_for_tier(rows, rarity=1)  # type: ignore[arg-type]
    assert [r.content_pool_id for r in got] == [1, 2]
