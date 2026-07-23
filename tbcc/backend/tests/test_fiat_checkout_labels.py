"""Fiat checkout label helpers — no Gumroad in user copy."""

from app.services.fiat_checkout_labels import (
    fiat_checkout_button_label,
    fiat_checkout_display_name,
    fiat_open_pay_button_label,
    scrub_gumroad_from_user_copy,
)


def test_defaults_never_say_gumroad():
    assert "gumroad" not in fiat_checkout_button_label().lower()
    assert "gumroad" not in fiat_checkout_display_name().lower()
    assert "gumroad" not in fiat_open_pay_button_label().lower()


def test_scrub_gumroad_from_user_copy():
    out = scrub_gumroad_from_user_copy("Pay on Gumroad today")
    assert "gumroad" not in out.lower()
    assert "Card / USD" in out
