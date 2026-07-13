"""Tests for bot funnel analytics rollup."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.models.loot import LootPlayerStats
from app.services.bot_funnel_analytics import bot_funnel_summary, loot_player_stats_summary


def test_loot_player_stats_summary_empty():
    db = MagicMock()
    db.query.return_value.all.return_value = []
    out = loot_player_stats_summary(db)
    assert out["unique_players"] == 0
    assert out["total_rolls"] == 0


def test_loot_player_stats_summary_aggregates():
    db = MagicMock()
    recent = LootPlayerStats(
        telegram_user_id=1,
        roll_count=3,
        free_pulls_used=2,
        last_roll_at=datetime.utcnow(),
    )
    old = LootPlayerStats(
        telegram_user_id=2,
        roll_count=1,
        free_pulls_used=1,
        last_roll_at=datetime.utcnow() - timedelta(days=30),
    )
    db.query.return_value.all.return_value = [recent, old]
    out = loot_player_stats_summary(db)
    assert out["unique_players"] == 2
    assert out["total_rolls"] == 4
    assert out["free_pulls_used"] == 3
    assert out["active_players_7d"] == 1


def test_bot_funnel_summary_includes_deep_links():
    db = MagicMock()
    db.query.return_value.all.return_value = []
    with patch(
        "app.services.bot_funnel_analytics.attribution_summary",
        return_value={"totals_by_type": {}, "range_days": 7},
    ):
        with patch.dict(
            "os.environ",
            {
                "TBCC_PAYMENT_BOT_USERNAME": "aofsubscriptions_bot",
                "TBCC_LOOT_BOT_USERNAME": "aof_lootgod_bot",
            },
            clear=False,
        ):
            out = bot_funnel_summary(db, days=7)
    assert out["deep_links"]["loot_paid_checkout"] == "https://t.me/aofsubscriptions_bot?start=loot"
    assert "attribution" in out
    assert "loot_players" in out
