"""Default shop table leads with impulse: 24h Loot Room keys, one recurring month.

Locked 2026-09-03 — the multi-month ladder ($48/$90/$168/$300) stays in the DB for
Gumroad Ping + grandfathered renewals but is filtered off the default keyboard.
"""

from __future__ import annotations

import pytest

from app.data.aof_vip_membership import (
    VIP_INTRO_PLAN_NAME,
    VIP_MEMBERSHIP_SKUS,
    default_hidden_vip_plan_names,
    featured_vip_sku,
    is_hidden_ladder_plan_name,
)
from app.services.payment_bot_settings_effective import DEFAULT_MAIN_MENU


def test_default_main_menu_opens_on_loot_keys():
    first_row = DEFAULT_MAIN_MENU[0]
    assert len(first_row) == 1
    assert first_row[0]["action"] == "menu_loot"
    assert "Loot Room" in first_row[0]["label"]


def test_insiders_reachable_but_not_the_first_tap():
    actions = [btn["action"] for row in DEFAULT_MAIN_MENU for btn in row]
    assert "menu_subscribe" in actions
    assert actions.index("menu_loot") < actions.index("menu_subscribe")


def test_multi_month_terms_are_hidden_from_default_grid():
    hidden = default_hidden_vip_plan_names()
    assert hidden == {
        "AOF VIP — 3 Months",
        "AOF VIP — 6 Months",
        "AOF VIP — 1 Year",
        "AOF VIP — 2 Years",
    }
    for name in hidden:
        assert is_hidden_ladder_plan_name(name)


def test_featured_month_and_intro_are_not_hidden():
    featured = featured_vip_sku()
    assert featured.duration_days == 30
    assert not is_hidden_ladder_plan_name(featured.name)
    assert not is_hidden_ladder_plan_name(VIP_INTRO_PLAN_NAME)
    assert not is_hidden_ladder_plan_name(None)


def test_hidden_terms_still_exist_as_skus():
    """Hide, never drop — Gumroad recurrence + price-cents lookups must keep resolving."""
    names = {sku.name for sku in VIP_MEMBERSHIP_SKUS}
    assert default_hidden_vip_plan_names() <= names
    assert len(VIP_MEMBERSHIP_SKUS) == 5


def test_env_escape_hatch_restores_full_ladder(monkeypatch):
    monkeypatch.setenv("TBCC_SHOW_FULL_VIP_LADDER", "1")
    assert not is_hidden_ladder_plan_name("AOF VIP — 2 Years")


@pytest.mark.parametrize(
    "fn",
    ["stars_howto_html", "stars_howto_plain"],
)
def test_stars_howto_stops_teaching_the_ladder_floor(fn):
    from app.data import telegram_stars_howto as mod

    body = getattr(mod, fn)()
    assert "/loot" in body
    assert "ladder" not in body.lower()
    assert "Standard renews" not in body


def test_subscribe_header_leads_with_monthly_not_intro():
    from app.services.fiat_checkout_labels import fiat_vip_ladder_intro_html

    body = fiat_vip_ladder_intro_html(include_intro=True)
    assert "ladder" not in body.lower()
    assert "$6/month" in body.replace(" ", "") or "$6</b>/month" in body
    assert body.index("$6") < body.index("$10")
    for include_intro in (False, True):
        assert "/month" in fiat_vip_ladder_intro_html(include_intro=include_intro)
