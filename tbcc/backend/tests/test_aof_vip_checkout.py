"""AOF VIP / Stars checkout URL resolution."""

from __future__ import annotations

from app.services.aof_vip_checkout import checkout_deep_link_payload, stars_pay_button_label


def test_checkout_deep_link_invoice_vs_menu():
    assert checkout_deep_link_payload(6, None) == "c6"
    assert checkout_deep_link_payload(6, None, menu=True) == "cm6"
    assert checkout_deep_link_payload(6, "ABC", menu=True) == "cm6_ABC"


def test_stars_pay_button_label():
    class _Plan:
        price_stars = 500
        name = "AOF VIP — 1 Month"

    assert stars_pay_button_label(_Plan()) == "Pay ⭐ 500"


def test_stars_pay_button_label_intro():
    from app.data.aof_vip_membership import VIP_INTRO_PLAN_NAME

    class _Plan:
        price_stars = 834
        name = VIP_INTRO_PLAN_NAME

    assert stars_pay_button_label(_Plan()) == "Insiders $10 · 834⭐"
