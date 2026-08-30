"""Tests for shared bot network discovery menus."""

from __future__ import annotations

from app.models.promo_affiliate_link import PromoAffiliateLink
from app.services.bot_network_discovery import (
    BOT_NETWORK_PLACEMENT,
    NetworkCallback,
    build_network_keyboard,
    network_menu_html,
    parse_network_callback,
    parse_network_start_payload,
)
from app.services.promo_affiliate_rotation import AFFILIATE_PLACEMENTS


def test_placement_registered():
    assert "bot_network_menu" in AFFILIATE_PLACEMENTS


def test_parse_network_start_payload():
    assert parse_network_start_payload("network") is True
    assert parse_network_start_payload("explore_aof") is True
    assert parse_network_start_payload("subscribe") is False


def test_parse_network_callback():
    assert parse_network_callback("aof_net:home") == NetworkCallback(view="home")
    assert parse_network_callback("aof_net:lanes:1") == NetworkCallback(view="lanes", lane_page=1)
    assert parse_network_callback("aof_net:ai") == NetworkCallback(view="ai")
    assert parse_network_callback("loot:roll") is None


def test_home_keyboard_has_sections(db):
    kb = build_network_keyboard(db, NetworkCallback(view="home"))
    flat = [btn for row in kb.inline_keyboard for btn in row]
    labels = [b.text for b in flat]
    callbacks = [b.callback_data for b in flat if b.callback_data]
    assert any("lanes" in (c or "") for c in callbacks)
    assert any("AI" in t for t in labels)
    assert any("Sponsors" in t for t in labels)
    assert any("Mainhub" in t for t in labels)


def test_lanes_keyboard_paginates(db):
    page0 = build_network_keyboard(db, NetworkCallback(view="lanes", lane_page=0))
    page1 = build_network_keyboard(db, NetworkCallback(view="lanes", lane_page=1))
    lane_urls0 = [
        b.url
        for row in page0.inline_keyboard
        for b in row
        if b.url and b.callback_data is None and "aofmainhub" not in (b.url or "")
    ]
    lane_urls1 = [
        b.url
        for row in page1.inline_keyboard
        for b in row
        if b.url and b.callback_data is None and "aofmainhub" not in (b.url or "")
    ]
    assert len(lane_urls0) == 8
    assert len(lane_urls1) >= 4
    assert lane_urls0 != lane_urls1


def test_sponsors_fallback_to_links_hub_sfw(db):
    row = PromoAffiliateLink(
        label="Test Sponsor",
        url="https://example.com/offer",
        payout_kind="cpa",
        active=True,
        placements_json='["links_hub_sfw"]',
        copy_template="{link}",
    )
    db.add(row)
    db.commit()
    kb = build_network_keyboard(db, NetworkCallback(view="sponsors"))
    flat = [b for row in kb.inline_keyboard for b in row]
    assert any("Test Sponsor" in b.text for b in flat)
    assert any("example.com" in (b.url or "") for b in flat)


def test_sponsors_prefer_bot_network_menu(db):
    row = PromoAffiliateLink(
        label="Bot Menu Sponsor",
        url="https://example.com/bot-only",
        payout_kind="cpa",
        active=True,
        placements_json=f'["{BOT_NETWORK_PLACEMENT}"]',
        copy_template="{link}",
    )
    db.add(row)
    db.commit()
    kb = build_network_keyboard(db, NetworkCallback(view="sponsors"))
    flat = [b for row in kb.inline_keyboard for b in row]
    assert any("Bot Menu Sponsor" in b.text for b in flat)


def test_network_menu_html_escapes_ampersand():
    text = network_menu_html(NetworkCallback(view="sponsors"))
    assert "partners</b>" in text
