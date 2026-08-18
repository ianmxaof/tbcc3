"""Tests for AOF VIP deal copy and subscription access."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.aof_vip_deal_copy import (
    build_vip_deal_caption_html,
    deal_stack_bullets_html,
    plan_invoice_description_short,
    pick_urgency_line,
)
from app.services.subscription_access import effective_link_resolver_tier, is_aof_vip_subscriber


def test_deal_stack_includes_companion_and_god_roll():
    bullets = deal_stack_bullets_html()
    joined = "\n".join(bullets)
    assert "Hall Pass" in joined
    assert "Daily God Roll" in joined
    assert "Companion" in joined or "aof_spicybot" in joined.lower()
    assert "viproll" in joined.lower()


def test_invoice_description_under_255_chars():
    desc = plan_invoice_description_short()
    assert len(desc) <= 255
    assert "Hall Pass" in desc


def test_build_vip_deal_caption_has_checkout_cta():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = MagicMock(
        price_stars=500, duration_days=30, name="AOF VIP — 1 Month"
    )
    with patch("app.services.aof_vip_deal_copy.resolve_group_access_plan_id", return_value=6):
        html = build_vip_deal_caption_html(db, 6)
    assert "AOF Insiders" in html
    assert "Pay ⭐" in html
    assert "What you get" in html
    assert "Hall Pass" in html


def test_build_vip_deal_caption_full_stack_is_default():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = MagicMock(
        price_stars=1500, duration_days=30, name="AOF VIP — 1 Month"
    )
    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("TBCC_VIP_CHECKOUT_CAPTION_MINIMAL", None)
        with patch("app.services.aof_vip_deal_copy.resolve_group_access_plan_id", return_value=6):
            html = build_vip_deal_caption_html(db, 6)
    assert "THE HALL PASS" in html
    assert "Public vs Insiders" in html


def test_build_vip_deal_caption_intro_variant():
    db = MagicMock()
    plan = MagicMock(price_stars=834, duration_days=30)
    plan.name = "AOF VIP — Intro Month"
    db.query.return_value.filter.return_value.first.return_value = plan
    with patch("app.services.aof_vip_deal_copy.resolve_group_access_plan_id", return_value=99):
        html = build_vip_deal_caption_html(db, 99)
    assert "FIRST 3 MONTHS" in html
    assert "one-time intro" in html.lower()
    assert "Daily God Roll" in html
    assert "THE HALL PASS" not in html


def test_build_vip_deal_caption_minimal_when_env_set():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = MagicMock(
        price_stars=500, duration_days=30, name="AOF VIP — 1 Month"
    )
    with patch.dict("os.environ", {"TBCC_VIP_CHECKOUT_CAPTION_MINIMAL": "1"}):
        with patch("app.services.aof_vip_deal_copy.resolve_group_access_plan_id", return_value=6):
            html = build_vip_deal_caption_html(db, 6)
    assert "AOF Insiders" in html
    assert "What you get" not in html


def test_pick_urgency_line_stable():
    a = pick_urgency_line(None, seed=0)
    b = pick_urgency_line(None, seed=0)
    assert a == b
    assert a


def test_is_aof_vip_subscriber_main_section_only():
    sub = MagicMock()
    sub.plan_id = 6
    plan_main = MagicMock()
    plan_main.product_type = "subscription"
    plan_main.bot_section = "main"
    db = MagicMock()

    with patch("app.services.subscription_access._active_rows", return_value=[sub]):
        db.query.return_value.filter.return_value.first.return_value = plan_main
        assert is_aof_vip_subscriber(db, 12345) is True

    plan_loot = MagicMock()
    plan_loot.product_type = "subscription"
    plan_loot.bot_section = "loot"
    with patch("app.services.subscription_access._active_rows", return_value=[sub]):
        db.query.return_value.filter.return_value.first.return_value = plan_loot
        assert is_aof_vip_subscriber(db, 12345) is False


def test_effective_link_resolver_tier_premium():
    sub = MagicMock()
    sub.expires_at = None
    sub.status = "active"
    db = MagicMock()
    with patch("app.services.subscription_access._active_rows", return_value=[sub]):
        assert effective_link_resolver_tier(db, 1) == "premium"
