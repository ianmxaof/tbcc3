"""Week 1 three-track: ledger lootlabs, crate tease, story flood-stop."""

from __future__ import annotations

import pytest

from app.services.income_ledger import ALL_SOURCES, SOURCE_LOOTLABS, _normalize_source
from app.services.link_gate_provider import _stable_provider_index, pick_gate_provider
from app.services.loot_free_tease import build_free_pull_tease_html, crate_origin_key_markup, pick_tease_lines
from app.services.telegram_story_oneshot import (
    account_lock_is_shared,
    flood_wait_seconds,
    identity_cadence_note,
    story_link_area,
)


def test_lootlabs_is_manual_source():
    assert SOURCE_LOOTLABS == "lootlabs"
    assert SOURCE_LOOTLABS in ALL_SOURCES
    assert _normalize_source("lootlabs") == "lootlabs"


def test_unknown_source_still_raises():
    with pytest.raises(ValueError, match="unknown_source"):
        _normalize_source("not_a_source")


def test_stable_provider_index_not_python_hash():
    a = _stable_provider_index("https://t.me/+same", 3)
    b = _stable_provider_index("https://t.me/+same", 3)
    assert a == b
    assert 0 <= a < 3


def test_pick_gate_seeded_stable_with_two_providers(monkeypatch):
    monkeypatch.setenv("TBCC_ADMAVEN_API_TOKEN", "tok")
    monkeypatch.setenv("TBCC_LINKVERTISE_PUBLISHER_ID", "1367336")
    monkeypatch.setenv("TBCC_LINK_GATE_PROVIDERS", "admaven,linkvertise")
    monkeypatch.setenv("TBCC_LINK_GATE_ROTATION", "round_robin")
    a = pick_gate_provider(seed="https://t.me/+alpha")
    b = pick_gate_provider(seed="https://t.me/+alpha")
    assert a == b


def test_crate_tease_four_of_five_honest():
    html = build_free_pull_tease_html(
        {"tease_modifiers": [{"label": "A"}, {"label": "B"}, {"label": "C"}, {"label": "D"}]},
        free_pulls_remaining=3,
        payment_bot_username="aofsubscriptions_bot",
    )
    assert "4 of 5" in html
    assert "not a hidden roll" in html
    assert "Tile 5" in html
    assert html.count("▣") >= 4


def test_crate_markup_src_loot_free():
    kb = crate_origin_key_markup(
        payment_bot_username="aofsubscriptions_bot",
        loot_bot_username="aof_lootgod_bot",
    )
    urls = [b.url for row in kb.inline_keyboard for b in row]
    assert any("start=loot" in (u or "") and "loot_free" not in (u or "") for u in urls)
    assert any("start=loot_free" in (u or "") for u in urls)


def test_pick_tease_lines_four_slots():
    import random

    lines = pick_tease_lines(random.Random(1), count=4, step=1)
    assert len(lines) == 4


class FloodWaitError(Exception):
    def __init__(self, seconds: int):
        self.seconds = seconds


def test_flood_wait_stops_and_alerts():

    assert flood_wait_seconds(FloodWaitError(42)) == 42
    assert flood_wait_seconds(ValueError("nope")) is None


def test_story_link_is_beacon_not_lv():
    url = story_link_area()
    assert "loot-free" in url or "loot_free" in url
    assert "linkvertise" not in url.lower()
    assert "link-hub" not in url.lower()


def test_identity_cadence_shared_lock(monkeypatch):
    monkeypatch.setenv("TBCC_TELEGRAM_ACCOUNT_LOCK", "1")
    assert account_lock_is_shared() is True
    assert "1/day" in identity_cadence_note(lock_contended=True)
