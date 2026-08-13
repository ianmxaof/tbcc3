"""Companion exhaustion CTA keyboard — loot + VIP rows."""

from __future__ import annotations

import pytest

from app.services.companion_monetize_cta import (
    companion_exhaustion_inline_keyboard_rows,
    companion_exhaustion_cta_html,
)


@pytest.fixture(autouse=True)
def _bot_env(monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_BOT_USERNAME", "aof_lootgod_bot")
    monkeypatch.setenv("TBCC_PAYMENT_BOT_USERNAME", "aofsubscriptions_bot")


def test_exhaustion_keyboard_has_loot_and_vip():
    rows = companion_exhaustion_inline_keyboard_rows()
    flat = [btn for row in rows for btn in row]
    texts = [b["text"] for b in flat]
    urls = [b["url"] for b in flat]
    assert any("Loot" in t for t in texts)
    assert any("VIP" in t for t in texts)
    assert any("loot_free" in u for u in urls)
    assert any("subscribe" in u for u in urls)


def test_exhaustion_cta_html_optional_undress():
    html = companion_exhaustion_cta_html(
        include_undress=True,
        undress_url="https://beacon.example/undress",
    )
    assert "Loot God" in html
    assert "undress" in html.lower() or "beacon.example" in html
