"""Payment post-purchase cross-sell keyboards."""

from __future__ import annotations

import pytest

from app.services.payment_post_purchase_cta import (
    classify_post_purchase_kind,
    post_purchase_inline_keyboard_rows,
)


@pytest.fixture(autouse=True)
def _bot_env(monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_BOT_USERNAME", "aof_lootgod_bot")
    monkeypatch.setenv("TBCC_PAYMENT_BOT_USERNAME", "aofsubscriptions_bot")
    monkeypatch.setenv("TBCC_COMPANION_BOT_USERNAME", "aof_spicybot_bot")


def test_classify_loot_key_purchase():
    kind = classify_post_purchase_kind(is_bundle=False, sub={"bot_section": "loot"})
    assert kind == "loot_key"


def test_vip_sub_cross_sell_has_loot_and_companion():
    rows = post_purchase_inline_keyboard_rows("vip_sub")
    flat = [btn for row in rows for btn in row]
    urls = [b["url"] for b in flat]
    assert any("loot_free" in u for u in urls)
    assert any("aof_spicybot_bot" in u for u in urls)


def test_loot_key_cross_sell_points_at_vip_intro():
    rows = post_purchase_inline_keyboard_rows("loot_key")
    flat = [btn for row in rows for btn in row]
    urls = [b["url"] for b in flat]
    assert any("cm10" in u or "subscribe" in u for u in urls)
    assert any("aof_spicybot_bot" in u for u in urls)


def test_bundle_cross_sell_has_loot_and_companion():
    kind = classify_post_purchase_kind(is_bundle=True, sub={})
    assert kind == "bundle"
    rows = post_purchase_inline_keyboard_rows(kind)
    urls = [btn["url"] for row in rows for btn in row]
    assert any("loot_free" in u for u in urls)
