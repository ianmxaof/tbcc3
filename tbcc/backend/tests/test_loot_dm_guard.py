"""Loot DM guard + user-safe errors."""

from __future__ import annotations

from app.services.loot_dm_guard import (
    loot_dm_only_enabled,
    loot_dm_redirect_html,
    should_redirect_loot_to_dm,
)
from app.services.loot_user_errors import loot_delivery_failed_user_html


def test_loot_dm_only_default_on():
    assert loot_dm_only_enabled() is True
    assert should_redirect_loot_to_dm(chat_type="supergroup") is True
    assert should_redirect_loot_to_dm(chat_type="private") is False


def test_loot_dm_redirect_copy():
    html = loot_dm_redirect_html(bot_username="aof_lootgod_bot")
    assert "DM-only" in html
    assert "aof_lootgod_bot" in html


def test_loot_delivery_failed_hides_operator_detail():
    text = loot_delivery_failed_user_html(
        headline="Pull failed",
        technical_note="media load failed — restart TBCC-Backend",
    )
    assert "TBCC-Backend" not in text
    assert "Pull failed" in text
    assert "/roll" in text
