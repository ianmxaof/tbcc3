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


def test_pools_for_tier_prefers_dedicated_loot_room_when_named():
    from app.services.loot_roll_preview import _pools_for_tier

    rows = [
        _Row(1, lo=1, hi=10),
        _Row(2, lo=1, hi=10),
        _Row(3, lo=1, hi=10),
    ]
    names = {
        1: "AOF ASS POOL",
        2: "LOOT ROOM FLOOR — AOF ASS",
        3: "AOF BLOWJOB POOL",
    }
    got = _pools_for_tier(rows, rarity=3, pool_names=names)  # type: ignore[arg-type]
    assert [r.content_pool_id for r in got] == [2]


def test_pools_for_tier_falls_back_to_shared_when_no_loot_room_names():
    rows = [_Row(1), _Row(2)]
    names = {1: "AOF ASS POOL", 2: "AOF MILF POOL"}
    got = _pools_for_tier(rows, rarity=1, pool_names=names)  # type: ignore[arg-type]
    assert [r.content_pool_id for r in got] == [1, 2]


def test_loot_album_max_items_caps_paid_draws(monkeypatch):
    from app.services.loot_roll_preview import loot_album_max_items

    monkeypatch.delenv("TBCC_LOOT_ALBUM_MAX", raising=False)
    assert loot_album_max_items() == 3
    monkeypatch.setenv("TBCC_LOOT_ALBUM_MAX", "12")
    assert loot_album_max_items() == 12


def test_kick_loot_stock_does_not_run_sync_vault_scan(monkeypatch):
    from app.services.loot_roll_preview import kick_loot_stock_background

    sync_calls: list[int] = []
    delay_calls: list[int] = []

    class _Task:
        def delay(self) -> None:
            delay_calls.append(1)

    monkeypatch.setattr(
        "app.services.sent_vault_lane_refill.refill_loot_pools_from_sent_vault_sync",
        lambda *a, **k: sync_calls.append(1) or 0,
    )
    monkeypatch.setattr(
        "app.workers.sent_vault_lane_refill_worker.refill_dry_lanes_from_sent_vault_task",
        _Task(),
    )
    kick_loot_stock_background()
    assert sync_calls == []
    assert delay_calls == [1]
