"""Telegram Stars how-to copy — impulse-first education + intro entry labeling."""

from __future__ import annotations

from app.data.aof_vip_membership import VIP_INTRO_PLAN_NAME
from app.data.telegram_stars_howto import (
    STARS_HOWTO_SNIPPET_TITLE,
    stars_howto_html,
    stars_howto_plain,
    stars_pay_entry_button_label,
    vip_intro_stars,
)
from app.services.fiat_checkout_labels import fiat_vip_ladder_intro_html


def test_vip_intro_stars_default_rate():
    assert vip_intro_stars() == 834


def test_stars_howto_teaches_card_purchase_and_leads_with_the_key():
    """Stars education anchors on the 24h key, not on a ladder floor (locked 2026-09-03)."""
    plain = stars_howto_plain()
    assert "credit/debit card" in plain.lower()
    assert "/loot" in plain
    assert "@aofsubscriptions_bot" in plain
    assert "ladder" not in plain.lower()
    html = stars_howto_html(compact=True)
    assert "My Stars" in html
    assert "/loot" in html
    assert "ladder" not in html.lower()


def test_entry_button_intro_vs_standard():
    assert stars_pay_entry_button_label(price_stars=834, plan_name=VIP_INTRO_PLAN_NAME) == "Insiders $10 · 834⭐"
    assert stars_pay_entry_button_label(price_stars=1500, plan_name="AOF VIP — 1 Month") == "Pay ⭐ 1500"


def test_ladder_intro_html_surfaces_ten():
    text = fiat_vip_ladder_intro_html(include_intro=True)
    assert "$10" in text
    assert "834" in text
    assert "Need Stars" in text or "Paying with Telegram Stars" in text
    assert STARS_HOWTO_SNIPPET_TITLE.startswith("[AOF]")
