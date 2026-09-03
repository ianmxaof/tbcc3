"""Compact VIP / credit-pack catalog keyboards — and what the default grid is allowed to show.

Sales table locked 2026-09-03: the shop leads with 24h Loot Room keys and one recurring
month. The multi-month ladder stays in the DB but must not reach the default keyboard,
and the intro term must not be the featured first row.
"""

import asyncio

from bots.payment_bot import _plan_checkout_keyboard_rows, fetch_plans


def _btn_cols(rows: list) -> list[int]:
    return [len(r) for r in rows]


def _plan(pid: int, name: str, stars: int, days: int) -> dict:
    return {
        "id": pid,
        "name": name,
        "price_stars": stars,
        "duration_days": days,
        "product_type": "subscription",
        "bot_section": "main",
        "is_active": True,
    }


# Full DB catalog: every term still exists as a row (Gumroad Ping / grandfathered renewals).
FULL_MAIN_CATALOG = [
    _plan(1, "AOF VIP — Intro Month", 834, 90),
    _plan(2, "AOF VIP — 1 Month", 500, 30),
    _plan(3, "AOF VIP — 3 Months", 4000, 90),
    _plan(4, "AOF VIP — 6 Months", 7500, 180),
    _plan(5, "AOF VIP — 1 Year", 14000, 365),
    _plan(6, "AOF VIP — 2 Years", 25000, 730),
]


def _main_catalog(monkeypatch, rows=None) -> list[dict]:
    async def _fake_raw():
        return list(FULL_MAIN_CATALOG if rows is None else rows)

    monkeypatch.setattr("bots.payment_bot._fetch_plans_raw", _fake_raw)
    return asyncio.run(fetch_plans(section="main"))


def test_default_catalog_hides_the_multi_month_ladder(monkeypatch):
    names = [p["name"] for p in _main_catalog(monkeypatch)]
    for buried in ("3 Months", "6 Months", "1 Year", "2 Years"):
        assert not any(buried in n for n in names), f"{buried} must not reach the default grid"


def test_default_catalog_does_not_feature_intro_first(monkeypatch):
    names = [p["name"] for p in _main_catalog(monkeypatch)]
    assert names, "the recurring month must still be listed"
    assert "Intro" not in names[0]
    assert names[0] == "AOF VIP — 1 Month"


def test_ladder_rows_survive_in_the_source_catalog(monkeypatch):
    """Hide, never drop — the filter is a view, not a delete."""
    _main_catalog(monkeypatch)
    assert len(FULL_MAIN_CATALOG) == 6


def test_env_escape_hatch_lists_every_term(monkeypatch):
    monkeypatch.setenv("TBCC_SHOW_FULL_VIP_LADDER", "1")
    names = [p["name"] for p in _main_catalog(monkeypatch)]
    assert any("2 Years" in n for n in names)


def test_vip_grid_one_row_per_tier_after_filtering():
    """Default grid is the impulse pair: standard month first, intro after it."""
    plans = [
        {"id": 2, "name": "Loot Room — 1 Month", "price_stars": 500, "duration_days": 30},
        {"id": 1, "name": "AOF VIP — Intro Month", "price_stars": 834, "duration_days": 90},
    ]
    rows = _plan_checkout_keyboard_rows(plans, multi_term=True, columns=3)
    assert len(rows) == 2
    assert all(c <= 3 for c in _btn_cols(rows))
    assert rows[0][0].callback_data == "plan_2"
    assert rows[1][0].callback_data == "plan_1"


def test_single_remaining_term_keeps_the_stars_howto(monkeypatch):
    """Hiding the ladder can leave one term — checkout must not lose the Stars education."""
    from bots import payment_bot

    sent = {}

    async def _fake_render(**kwargs):
        sent.update(kwargs)

    class _Msg:
        chat_id = 1

    class _Ctx:
        bot = object()

    monkeypatch.setattr(payment_bot, "render_payment_ui", _fake_render)
    asyncio.run(
        payment_bot.send_simple_plan_checkout(
            _Msg(),
            _Ctx(),
            [_plan(2, "AOF VIP — 1 Month", 500, 30)],
        )
    )
    assert sent["parse_mode"] == "HTML"
    assert "My Stars" in sent["text"]
    assert "Loot Room — 1 Month" in sent["text"]


def test_companion_credits_grid_two_rows():
    plans = [
        {"id": 10, "name": "Spicy Reveal — 5 Pack", "price_stars": 110, "product_type": "companion_credits"},
        {"id": 11, "name": "Spicy Reveal — 15 Pack", "price_stars": 300, "product_type": "companion_credits"},
        {"id": 12, "name": "Spicy Reveal — 50 Pack", "price_stars": 900, "product_type": "companion_credits"},
    ]
    rows = _plan_checkout_keyboard_rows(plans, credits=True, columns=3)
    assert len(rows) == 2
    assert _btn_cols(rows) == [3, 3]
    assert rows[0][0].callback_data == "credit_10"
    assert rows[1][0].callback_data == "ext_credit_10"


def test_single_credit_pack_horizontal():
    plans = [
        {"id": 10, "name": "Spicy Reveal — 5 Pack", "price_stars": 110, "product_type": "companion_credits"},
    ]
    rows = _plan_checkout_keyboard_rows(plans, credits=True, columns=3)
    assert len(rows) == 1
    assert len(rows[0]) >= 2
