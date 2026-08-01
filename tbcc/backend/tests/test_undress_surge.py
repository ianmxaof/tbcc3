"""Undress surge spike detection + blast."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.services import undress_surge as surge


def test_is_undress_signal_matches_refs():
    assert surge.is_undress_signal(source_ref="src_aff_undress_ai_dm")
    assert surge.is_undress_signal(link_label="Undress AI bot")
    assert surge.is_undress_signal(url="https://nodress.site/tg/bot")
    assert not surge.is_undress_signal(source_ref="src_aff_bangbros_footer")


def test_record_undress_signal_counts_in_window(monkeypatch):
    store: dict[str, dict] = {"z": {}, "kv": {}}

    class FakeRedis:
        def zadd(self, key, mapping):
            store["z"].update(mapping)

        def zremrangebyscore(self, key, _min, _max):
            return 0

        def zcard(self, key):
            return len(store["z"])

    monkeypatch.setattr(surge, "_redis", lambda: FakeRedis())
    monkeypatch.setenv("TBCC_UNDRESS_SURGE_ENABLED", "1")
    monkeypatch.setenv("TBCC_UNDRESS_SPIKE_HITS", "3")
    assert surge.record_undress_signal("beacon") == 1
    assert surge.record_undress_signal("served") == 2


def test_spike_state_threshold(monkeypatch):
    monkeypatch.setattr(
        surge,
        "_redis",
        lambda: MagicMock(
            zremrangebyscore=MagicMock(),
            zcard=MagicMock(return_value=9),
            get=MagicMock(return_value=None),
        ),
    )
    monkeypatch.setenv("TBCC_UNDRESS_SPIKE_HITS", "4")
    state = surge.spike_state()
    assert state["spike_active"] is True
    assert state["hits_in_window"] == 9


def test_maybe_auto_surge_below_threshold(monkeypatch):
    monkeypatch.setenv("TBCC_UNDRESS_SPIKE_HITS", "10")
    assert surge.maybe_auto_surge_from_spike(hits=5) is None


def test_build_surge_html_contains_loot_vip(monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_BOT_USERNAME", "aof_lootgod_bot")
    monkeypatch.setenv("TBCC_PAYMENT_BOT_USERNAME", "aofsubscriptions_bot")
    monkeypatch.setattr(surge, "affiliate_undress_url_wrapped", lambda **_: "https://example.com/undress")
    db = MagicMock()
    html = surge.build_surge_html(db)
    assert "Loot God" in html
    assert "VIP" in html
    assert "undress" in html.lower() or "example.com" in html
