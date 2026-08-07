"""Free-pull midpoint upsell on complimentary pull 3/5."""

from __future__ import annotations

from app.services.loot_inline_keyboards import (
    build_loot_roll_inline_markup,
    free_pull_midpoint_upsell_row,
    should_show_free_pull_midpoint,
)


def test_midpoint_only_on_pull_three_with_remaining():
    assert should_show_free_pull_midpoint(free_pull_number=3, free_pulls_remaining=2)
    assert not should_show_free_pull_midpoint(free_pull_number=2, free_pulls_remaining=2)
    assert not should_show_free_pull_midpoint(free_pull_number=3, free_pulls_remaining=0)


def test_midpoint_row_has_key_and_vip():
    row = free_pull_midpoint_upsell_row(payment_bot_username="aofsubscriptions_bot")
    urls = [btn.url for btn in row]
    assert any("start=loot" in u for u in urls)
    assert any("subscribe" in u for u in urls)


def test_build_markup_inserts_midpoint_on_pull_three(monkeypatch):
    monkeypatch.setenv("TBCC_PAYMENT_BOT_USERNAME", "aofsubscriptions_bot")
    kb = build_loot_roll_inline_markup(free_pull_number=3, free_pulls_remaining=2, free_pull_limit=5)
    flat_url = [btn.url for row in kb.inline_keyboard for btn in row if btn.url]
    assert sum(1 for u in flat_url if "start=loot" in u) >= 1
    assert any("subscribe" in u for u in flat_url)


def test_build_markup_skips_midpoint_on_pull_two(monkeypatch):
    monkeypatch.setenv("TBCC_PAYMENT_BOT_USERNAME", "aofsubscriptions_bot")
    kb_early = build_loot_roll_inline_markup(free_pull_number=2, free_pulls_remaining=3, free_pull_limit=5)
    texts_early = [btn.text for row in kb_early.inline_keyboard for btn in row]
    assert not any("Halfway" in t or "daily roll" in t for t in texts_early)


def test_high_tier_key_roll_adds_vip_row(monkeypatch):
    monkeypatch.setenv("TBCC_PAYMENT_BOT_USERNAME", "aofsubscriptions_bot")

    from bots.loot_bot import _loot_inline_keyboard

    kb = _loot_inline_keyboard({}, rarity_tier=8)
    urls = [btn.url for row in kb.inline_keyboard for btn in row if btn.url]
    assert any("subscribe" in u for u in urls)
