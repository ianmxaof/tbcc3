"""Tests for @aofmainhub daily channel spotlight."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.lane_of_the_day import SPOTLIGHT_HOOKS
from app.services.mainhub_channel_spotlight import (
    build_spotlight_caption_html,
    build_spotlight_inline_keyboard,
    eligible_spotlight_lane_keys,
    spotlight_lane_for_day,
)


def test_spotlight_lane_round_robin_cycles():
    keys = eligible_spotlight_lane_keys()
    assert keys
    assert "inbox" not in keys
    assert "packs" not in keys
    assert spotlight_lane_for_day(0) == keys[0]
    assert spotlight_lane_for_day(len(keys)) == keys[0]
    assert spotlight_lane_for_day(1) == keys[1 % len(keys)]


def test_spotlight_hooks_cover_all_eligible_lanes():
    keys = eligible_spotlight_lane_keys()
    missing = [k for k in keys if k not in SPOTLIGHT_HOOKS]
    assert not missing, f"missing SPOTLIGHT_HOOKS for: {missing}"


@patch("app.services.mainhub_channel_spotlight.lv_urls")
@patch("app.services.mainhub_channel_spotlight.build_addlist_footer")
def test_spotlight_caption_includes_hook_and_promo(mock_footer, mock_lv):
    mock_lv.return_value = {"milf": "https://gate.example/milf", "addlist": "https://gate.example/add"}
    mock_footer.return_value = "\n\nFOOTER"
    db = MagicMock()
    html = build_spotlight_caption_html(db, network_key="milf", day_ordinal=20260802)
    assert "CHANNEL OF THE DAY" in html or "WINDOW SHOP" in html or "FEATURED" in html
    assert "mature curves" in html.lower() or "MILF" in html
    assert "AOF MILF" in html
    assert "gate.example/milf" in html
    assert "FOOTER" in html


@patch("app.services.mainhub_channel_spotlight.lv_urls")
def test_spotlight_keyboard_has_wrapped_join(mock_lv):
    mock_lv.return_value = {
        "ass": "https://gate.example/ass",
        "addlist": "https://gate.example/add",
        "loot": "https://gate.example/loot",
    }
    kb = build_spotlight_inline_keyboard(MagicMock(), network_key="ass")
    flat = [btn for row in kb for btn in row]
    urls = {b["url"] for b in flat}
    assert "https://gate.example/ass" in urls
    assert any("aofmainhub" in u for u in urls)


@patch("app.services.mainhub_channel_spotlight._already_sent_today", return_value=True)
def test_queue_spotlight_idempotent_skip(mock_sent):
    from datetime import datetime, timezone

    from app.services.mainhub_channel_spotlight import queue_mainhub_channel_spotlight

    db = MagicMock()
    with patch("app.services.mainhub_channel_spotlight.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 8, 2, 15, 0, tzinfo=timezone.utc)
        mock_dt.strftime = datetime.strftime
        report = queue_mainhub_channel_spotlight(db, force=False)

    assert report.get("skipped") is True
    assert report.get("reason") == "already_sent"
    mock_sent.assert_called_once()
