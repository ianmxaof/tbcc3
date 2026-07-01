"""Tests for the growth content-signal engine (content_signals.py).

Uses the real in-memory SQLite `db` fixture from conftest and inserts real rows
so the SQLAlchemy query paths (distinct/limit/filter) are exercised, not mocked.
Only Redis is faked (the engine's sole external side-effect for digest tracking).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

# Importing the models registers their tables on Base.metadata so the conftest
# `db` fixture's create_all() builds them under SQLite.
from app.models.channel import Channel
from app.models.growth_attribution_event import GrowthAttributionEvent  # noqa: F401
from app.models.post_delivery_metric import PostDeliveryMetric
from app.models.scheduled_text_post import ScheduledTextPost  # noqa: F401
from app.services import content_signals as cs


def _seed_peak_hour_deliveries(db) -> None:
    """5 high-view posts at hour 20, 5 low-view posts at hour 3 (same channel).

    Network avg lands ~120; hour 20 (avg 200) clears the 1.3x medium-confidence
    bar while hour 3 (avg 40) falls below it -> exactly one surviving signal.
    """
    db.add(Channel(id=1, name="Lane A", identifier="@lane_a"))
    now = datetime.utcnow()
    for i in range(5):
        db.add(
            PostDeliveryMetric(
                created_at=now - timedelta(days=1, minutes=i),
                event_type="scheduled_post_sent",
                channel_id=1,
                posted_hour_local=20,
                views_latest=200,
            )
        )
    for i in range(5):
        db.add(
            PostDeliveryMetric(
                created_at=now - timedelta(days=1, minutes=100 + i),
                event_type="scheduled_post_sent",
                channel_id=1,
                posted_hour_local=3,
                views_latest=40,
            )
        )
    db.commit()


class FakeRedis:
    """Minimal get/set stand-in for the digest tracker."""

    def __init__(self, initial: dict[str, str] | None = None):
        self.store: dict[str, str] = dict(initial or {})

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = str(value)


# --------------------------------------------------------------------------- #
# compute_strong_signals — ranking
# --------------------------------------------------------------------------- #

def test_compute_strong_signals_ranks_peak_hour(db):
    _seed_peak_hour_deliveries(db)
    report = cs.compute_strong_signals(db, days=14)

    assert report["ok"] is True
    assert report["enabled"] is True
    assert report["signal_count"] >= 1

    top = report["signals"][0]
    assert top["signal_type"] == "peak_post_hour"
    assert top["hour_local"] == 20
    assert top["recommendation"]
    # The weak hour-3 bucket must be filtered out.
    assert all(s.get("hour_local") != 3 for s in report["signals"])
    # Sorted by descending strength.
    strengths = [float(s["strength"]) for s in report["signals"]]
    assert strengths == sorted(strengths, reverse=True)


def test_compute_strong_signals_disabled(db, monkeypatch):
    monkeypatch.setenv("TBCC_GROWTH_SIGNALS_ENABLED", "0")
    report = cs.compute_strong_signals(db, days=14)
    assert report == {"ok": True, "enabled": False, "signals": []}


def test_compute_strong_signals_empty_db(db):
    report = cs.compute_strong_signals(db, days=14)
    assert report["ok"] is True
    assert report["signal_count"] == 0
    assert report["signals"] == []


# --------------------------------------------------------------------------- #
# _digest_hash — stability + change detection
# --------------------------------------------------------------------------- #

def test_digest_hash_stable_and_length():
    payload = {"signals": [{"signal_type": "peak_post_hour", "hour_local": 20, "strength": 0.5}]}
    h1 = cs._digest_hash(payload)
    h2 = cs._digest_hash(payload)
    assert h1 == h2
    assert len(h1) == 16


def test_digest_hash_ignores_non_signal_fields():
    a = {"signals": [{"x": 1}], "computed_at": "2026-01-01T00:00:00Z"}
    b = {"signals": [{"x": 1}], "computed_at": "2026-12-31T00:00:00Z"}
    # Only the signals list feeds the digest, so timestamps must not change it.
    assert cs._digest_hash(a) == cs._digest_hash(b)


def test_digest_hash_changes_with_signals():
    a = {"signals": [{"signal_type": "peak_post_hour", "hour_local": 20}]}
    b = {"signals": [{"signal_type": "peak_post_hour", "hour_local": 21}]}
    assert cs._digest_hash(a) != cs._digest_hash(b)


def test_digest_hash_empty_signals():
    assert cs._digest_hash({}) == cs._digest_hash({"signals": []})


# --------------------------------------------------------------------------- #
# format_signals_markdown — output shape
# --------------------------------------------------------------------------- #

def test_format_markdown_with_signals():
    report = {
        "lookback_days": 14,
        "timezone": "UTC",
        "network_avg_views": 120.0,
        "signals": [
            {
                "signal_type": "peak_post_hour",
                "confidence": "medium",
                "strength": 0.5,
                "recommendation": "Bias recurring posts toward 20:00.",
            }
        ],
    }
    md = cs.format_signals_markdown(report)
    assert md.startswith("# TBCC growth signals")
    assert "peak_post_hour" in md
    assert "Bias recurring posts toward 20:00." in md
    assert "1. **peak_post_hour**" in md


def test_format_markdown_no_signals():
    md = cs.format_signals_markdown({"lookback_days": 14, "timezone": "UTC", "signals": []})
    assert "# TBCC growth signals" in md
    assert "No high-confidence signals" in md


# --------------------------------------------------------------------------- #
# tick_growth_signals — digest_changed edge cases
# --------------------------------------------------------------------------- #

def test_tick_first_run_no_prev_digest(db, monkeypatch):
    _seed_peak_hour_deliveries(db)
    fake = FakeRedis()
    monkeypatch.setattr(cs, "_redis_client", lambda: fake)

    result = cs.tick_growth_signals(db, refresh_views=False, push_inbox_on_change=False)

    assert result["ok"] is True
    # No previous digest -> not "changed" (avoids a first-run false alarm).
    assert result["digest_changed"] is False
    assert result["digest"]
    # Digest is now persisted for the next tick.
    assert fake.store[cs.REDIS_LAST_DIGEST] == result["digest"]
    assert cs.REDIS_LAST_TICK in fake.store


def test_tick_detects_digest_change(db, monkeypatch):
    _seed_peak_hour_deliveries(db)
    fake = FakeRedis({cs.REDIS_LAST_DIGEST: "stale_digest_value"})
    monkeypatch.setattr(cs, "_redis_client", lambda: fake)

    result = cs.tick_growth_signals(db, refresh_views=False, push_inbox_on_change=False)

    assert result["digest_changed"] is True
    assert result["digest"] != "stale_digest_value"


def test_tick_unchanged_when_prev_matches(db, monkeypatch):
    _seed_peak_hour_deliveries(db)
    # Prime redis with the digest this exact report will produce.
    report = cs.compute_strong_signals(db)
    digest = cs._digest_hash(report)
    fake = FakeRedis({cs.REDIS_LAST_DIGEST: digest})
    monkeypatch.setattr(cs, "_redis_client", lambda: fake)

    result = cs.tick_growth_signals(db, refresh_views=False, push_inbox_on_change=False)
    assert result["digest"] == digest
    assert result["digest_changed"] is False


def test_tick_disabled_short_circuits(db, monkeypatch):
    monkeypatch.setenv("TBCC_GROWTH_SIGNALS_ENABLED", "off")
    result = cs.tick_growth_signals(db, refresh_views=False)
    assert result == {"ok": True, "enabled": False, "skipped": True}
