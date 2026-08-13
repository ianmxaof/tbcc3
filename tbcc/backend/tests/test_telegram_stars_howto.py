"""Telegram Stars how-to copy + $10 VIP entry labeling."""

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


def test_stars_howto_mentions_card_and_ten():
    plain = stars_howto_plain()
    assert "credit/debit card" in plain.lower() or "credit/debit card" in plain
    assert "$10" in plain
    assert "834" in plain
    assert "@aofsubscriptions_bot" in plain
    html = stars_howto_html(compact=True)
    assert "$10" in html
    assert "834" in html
    assert "My Stars" in html


def test_entry_button_intro_vs_standard():
    assert stars_pay_entry_button_label(price_stars=834, plan_name=VIP_INTRO_PLAN_NAME) == "VIP $10 · 834⭐"
    assert stars_pay_entry_button_label(price_stars=1500, plan_name="AOF VIP — 1 Month") == "Pay ⭐ 1500"


def test_ladder_intro_html_surfaces_ten():
    text = fiat_vip_ladder_intro_html(include_intro=True)
    assert "$10" in text
    assert "834" in text
    assert "Need Stars" in text or "Paying with Telegram Stars" in text
    assert STARS_HOWTO_SNIPPET_TITLE.startswith("[AOF]")
