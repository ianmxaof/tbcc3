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
    assert any("Buy another reveal" in line for line in lines)
    assert any("invite friends" in line.lower() for line in lines)


def test_reveal_paywall_lines_mention_first_reveal_when_strict(monkeypatch):
    monkeypatch.setenv("TBCC_COMPANION_STARS_ENABLED", "0")
    monkeypatch.setenv("TBCC_COMPANION_REFERRAL_ENABLED", "1")
    monkeypatch.setenv("TBCC_COMPANION_REFERRAL_REQUIRE_INVITEE_REVEAL", "1")
    lines = paywall.reveal_paywall_lines()
    assert any("first reveal" in line for line in lines)
