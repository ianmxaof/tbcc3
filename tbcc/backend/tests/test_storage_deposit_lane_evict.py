"""Storage Hub deposit lane hygiene — batch selection + duplicate eviction."""

from __future__ import annotations

from app.services.storage_sent_cache import storage_deposit_lane_evict_enabled


def test_lane_evict_enabled_by_default():
    assert storage_deposit_lane_evict_enabled() is True


def test_lane_evict_disabled_via_env(monkeypatch):
    monkeypatch.setenv("TBCC_STORAGE_DEPOSIT_LANE_EVICT", "0")
    assert storage_deposit_lane_evict_enabled() is False
