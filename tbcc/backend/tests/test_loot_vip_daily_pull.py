"""Tests for VIP daily god roll eligibility."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.services.loot_vip_daily_pull import (
    roll_vip_daily_rarity_tier,
    vip_daily_pull_available,
    vip_daily_pull_used_today,
)


def test_roll_vip_daily_min_tier_floor():
    rng = __import__("random").Random(42)
    db = MagicMock()
    with patch("app.services.loot_vip_daily_pull.get_lifetime_roll_index", return_value=0):
        with patch("app.services.loot_vip_daily_pull.vip_daily_min_tier", return_value=7):
            tier = roll_vip_daily_rarity_tier(rng, db, 1)
    assert tier >= 7
    assert tier <= 10


def test_vip_daily_used_today():
    row = MagicMock()
    row.vip_daily_pull_at = datetime.utcnow()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row
    assert vip_daily_pull_used_today(db, 99) is True


def test_vip_daily_not_used_yesterday():
    row = MagicMock()
    row.vip_daily_pull_at = datetime.utcnow() - timedelta(days=1)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row
    assert vip_daily_pull_used_today(db, 99) is False


def test_vip_daily_available_requires_subscriber():
    db = MagicMock()
    with patch("app.services.loot_vip_daily_pull.vip_daily_pull_enabled", return_value=True):
        with patch("app.services.loot_vip_daily_pull.is_aof_vip_subscriber", return_value=False):
            assert vip_daily_pull_available(db, 1) is False
        with patch("app.services.loot_vip_daily_pull.is_aof_vip_subscriber", return_value=True):
            with patch("app.services.loot_vip_daily_pull.vip_daily_pull_used_today", return_value=False):
                assert vip_daily_pull_available(db, 1) is True
