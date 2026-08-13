"""Tests for companion reveal paywall copy helpers."""

from __future__ import annotations

import pytest

from app.services import companion_reveal_paywall as paywall


def test_reveal_paywall_lines_only_when_exhausted_context(monkeypatch):
    monkeypatch.setenv("TBCC_COMPANION_STARS_ENABLED", "1")
    monkeypatch.setenv("TBCC_COMPANION_STARS_PER_PHOTO", "25")
    monkeypatch.setenv("TBCC_COMPANION_REFERRAL_ENABLED", "1")
    monkeypatch.setenv("TBCC_COMPANION_REFERRAL_BONUS_PHOTOS", "1")
    lines = paywall.reveal_paywall_lines()
    assert any("Buy one reveal" in line for line in lines)
    assert any("invite friends" in line.lower() for line in lines)


def test_reveal_paywall_lines_mention_first_reveal_when_strict(monkeypatch):
    monkeypatch.setenv("TBCC_COMPANION_STARS_ENABLED", "0")
    monkeypatch.setenv("TBCC_COMPANION_REFERRAL_ENABLED", "1")
    monkeypatch.setenv("TBCC_COMPANION_REFERRAL_REQUIRE_INVITEE_REVEAL", "1")
    lines = paywall.reveal_paywall_lines()
    assert any("first reveal" in line for line in lines)


def test_reveal_paywall_keyboard_has_loot_and_vip(monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_BOT_USERNAME", "aof_lootgod_bot")
    monkeypatch.setenv("TBCC_PAYMENT_BOT_USERNAME", "aofsubscriptions_bot")
    monkeypatch.setenv("TBCC_COMPANION_REFERRAL_ENABLED", "0")
    kb = paywall.reveal_paywall_keyboard(bot_username="aof_spicybot_bot", user_id=42)
    assert kb is not None
    urls = [btn.url for row in kb.inline_keyboard for btn in row if btn.url]
    assert any("loot_free" in u for u in urls)
    assert any("subscribe" in u for u in urls)
