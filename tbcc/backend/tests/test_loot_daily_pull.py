"""Daily micro-pull — enable gate, tier cap, streak advance and bonus payout."""

import random
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.models.loot import LootPlayerStats
from app.services.loot_daily_pull import (
    commit_daily_pull,
    daily_pull_enabled,
    daily_pull_max_tier,
    daily_pull_used_today,
    next_streak_value,
    streak_bonus_every,
)
from app.services.loot_tier_catalog import DAILY_PULL_MAX_TIER, roll_daily_rarity_tier


@pytest.fixture(autouse=True)
def _enable_daily(monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_DAILY_PULL_ENABLED", "1")
    monkeypatch.setenv("TBCC_LOOT_DAILY_STREAK_BONUS_EVERY", "7")
    monkeypatch.delenv("TBCC_LOOT_DAILY_PULL_MAX_TIER", raising=False)


def test_daily_pull_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TBCC_LOOT_DAILY_PULL_ENABLED", raising=False)
    assert daily_pull_enabled() is False


def test_daily_pull_enabled_by_env():
    assert daily_pull_enabled() is True


def test_daily_pull_max_tier_clamped(monkeypatch):
    assert daily_pull_max_tier() == DAILY_PULL_MAX_TIER
    monkeypatch.setenv("TBCC_LOOT_DAILY_PULL_MAX_TIER", "99")
    assert daily_pull_max_tier() == 5
    monkeypatch.setenv("TBCC_LOOT_DAILY_PULL_MAX_TIER", "junk")
    assert daily_pull_max_tier() == DAILY_PULL_MAX_TIER


def test_roll_daily_rarity_tier_never_exceeds_cap():
    rng = random.Random(1234)
    rolls = [roll_daily_rarity_tier(rng, max_tier=2) for _ in range(400)]
    assert set(rolls) <= {1, 2}
    # Bottom-weighted: tier 1 must dominate so this never feels like a free pull.
    assert rolls.count(1) > rolls.count(2)


def test_next_streak_value_consecutive_day():
    yesterday = datetime.utcnow() - timedelta(days=1)
    assert next_streak_value(yesterday, 4) == 5


def test_next_streak_value_gap_resets():
    stale = datetime.utcnow() - timedelta(days=3)
    assert next_streak_value(stale, 9) == 1


def test_next_streak_value_first_ever():
    assert next_streak_value(None, 0) == 1


def test_next_streak_value_same_day_holds():
    assert next_streak_value(datetime.utcnow(), 6) == 6


def test_daily_pull_used_today_true_for_today():
    db = MagicMock()
    row = LootPlayerStats(telegram_user_id=1, daily_pull_at=datetime.utcnow())
    db.query.return_value.filter.return_value.first.return_value = row
    assert daily_pull_used_today(db, 1) is True


def test_daily_pull_used_today_false_for_yesterday():
    db = MagicMock()
    row = LootPlayerStats(telegram_user_id=1, daily_pull_at=datetime.utcnow() - timedelta(days=1))
    db.query.return_value.filter.return_value.first.return_value = row
    assert daily_pull_used_today(db, 1) is False


def _commit_with_row(monkeypatch, row, preview=None):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row
    monkeypatch.setattr("app.services.loot_daily_pull.is_loot_operator", lambda _uid: False)
    monkeypatch.setattr(
        "app.services.loot_daily_pull.mark_daily_pull_media_seen",
        lambda *_a, **_k: None,
    )
    payload = preview or {"ok": True, "rarity_tier": 1, "media": [{"id": 5}]}
    return commit_daily_pull(db, 1, payload)


def test_commit_daily_pull_advances_streak(monkeypatch):
    row = LootPlayerStats(
        telegram_user_id=1,
        daily_pull_at=datetime.utcnow() - timedelta(days=1),
        daily_streak_days=2,
        daily_streak_best=2,
        bonus_free_pulls=0,
    )
    out = _commit_with_row(monkeypatch, row)
    assert out["streak_days"] == 3
    assert row.daily_streak_best == 3
    assert out["bonus_free_pulls_awarded"] == 0
    assert row.bonus_free_pulls == 0


def test_commit_daily_pull_pays_bonus_on_seventh_day(monkeypatch):
    row = LootPlayerStats(
        telegram_user_id=1,
        daily_pull_at=datetime.utcnow() - timedelta(days=1),
        daily_streak_days=6,
        daily_streak_best=6,
        bonus_free_pulls=0,
    )
    out = _commit_with_row(monkeypatch, row)
    assert out["streak_days"] == 7
    assert out["bonus_free_pulls_awarded"] == 1
    assert row.bonus_free_pulls == 1


def test_commit_daily_pull_keeps_best_streak_after_reset(monkeypatch):
    row = LootPlayerStats(
        telegram_user_id=1,
        daily_pull_at=datetime.utcnow() - timedelta(days=5),
        daily_streak_days=9,
        daily_streak_best=9,
        bonus_free_pulls=0,
    )
    out = _commit_with_row(monkeypatch, row)
    assert out["streak_days"] == 1
    assert row.daily_streak_best == 9


def test_commit_daily_pull_noop_on_failed_preview(monkeypatch):
    row = LootPlayerStats(telegram_user_id=1, daily_streak_days=3)
    out = _commit_with_row(monkeypatch, row, preview={"ok": False, "reason": "no_media_candidates"})
    assert out["ok"] is False
    assert row.daily_streak_days == 3


def test_streak_bonus_every_disabled(monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_DAILY_STREAK_BONUS_EVERY", "0")
    assert streak_bonus_every() == 0
    row = LootPlayerStats(
        telegram_user_id=1,
        daily_pull_at=datetime.utcnow() - timedelta(days=1),
        daily_streak_days=6,
        bonus_free_pulls=0,
    )
    out = _commit_with_row(monkeypatch, row)
    assert out["bonus_free_pulls_awarded"] == 0
    assert row.bonus_free_pulls == 0
