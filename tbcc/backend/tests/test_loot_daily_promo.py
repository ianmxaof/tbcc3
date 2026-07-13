"""Tests for loot daily promo monetization deep links."""

from unittest.mock import MagicMock, patch

from app.services.loot_daily_promo import build_loot_daily_promo_html, loot_daily_promo_inline_keyboard


def test_loot_daily_promo_keyboard_paid_first():
    kb = loot_daily_promo_inline_keyboard("aof_lootgod_bot", payment_bot_username="aofsubscriptions_bot")
    rows = kb["inline_keyboard"]
    assert len(rows) == 2
    assert "24h room access" in rows[0][0]["text"]
    assert rows[0][0]["url"] == "https://t.me/aofsubscriptions_bot?start=loot"
    assert rows[1][0]["url"] == "https://t.me/aof_lootgod_bot?start=loot_free"


@patch("app.services.loot_daily_promo.get_effective_loot_bot_settings")
def test_loot_daily_promo_html_leads_with_paid(mock_eff):
    mock_eff.return_value = {
        "bot_username": "aof_lootgod_bot",
        "daily_promo_intro_html": "",
        "primary_loot_room_invite_url": "",
    }
    with patch.dict("os.environ", {"TBCC_PAYMENT_BOT_USERNAME": "aofsubscriptions_bot"}, clear=False):
        html = build_loot_daily_promo_html(MagicMock())
    assert "24h access via Stars" in html
    assert "aofsubscriptions_bot" in html
    assert "start=loot" in html
