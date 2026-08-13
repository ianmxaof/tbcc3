"""Tests for Loot Room growth menu variant."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.aof_links_hub_menu_variants import (
    LOOT_VARIANTS,
    _interactive_menu_caption,
    build_loot_inline_buttons,
    build_loot_menu_variant,
)


@patch("app.services.aof_links_hub_menu_variants.lv_urls")
def test_loot_menu_caption_bare_invite_and_18_plus(mock_lv):
    mock_lv.return_value = {}
    cap = _interactive_menu_caption("loot", "GROWTH REVEAL", variant="v5")
    assert "18+" in cap
    assert "NSFW" in cap
    assert "97f4Crv3G1RkMGU5" in cap or "t.me/+" in cap


@patch("app.services.aof_links_hub_menu_variants.lv_urls")
def test_loot_inline_buttons_include_monetization(mock_lv):
    mock_lv.return_value = {"ai": "https://gate/ai", "addlist": "https://gate/add"}
    kb = build_loot_inline_buttons(MagicMock())
    flat = [b for row in kb for b in row]
    texts = {b["text"] for b in flat}
    urls = {b["url"] for b in flat}
    assert any("Free roll" in t for t in texts)
    assert any("loot_free" in u for u in urls)
    assert any("start=loot" in u for u in urls)
    assert any("subscribe" in u for u in urls)


def test_loot_variants_build():
    db = MagicMock()
    for v in LOOT_VARIANTS:
        menu = build_loot_menu_variant(db, v)
        assert menu.kind == "loot"
        assert menu.title
        assert "LOOT" in menu.html.upper()
