"""Lane-of-the-day alignment — shared seed for mainhub + liveness."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.lane_of_the_day import (
    SPOTLIGHT_HOOKS,
    build_liveness_featured_drop_ticker,
    build_liveness_featured_spotlight,
    eligible_lane_keys,
    lane_of_the_day_key,
    lane_of_day_align_enabled,
)


def test_lane_of_the_day_round_robin():
    keys = eligible_lane_keys()
    assert keys
    assert lane_of_the_day_key(0) == keys[0]
    assert lane_of_the_day_key(len(keys)) == keys[0]


def test_hooks_cover_eligible_lanes():
    missing = [k for k in eligible_lane_keys() if k not in SPOTLIGHT_HOOKS]
    assert not missing


@patch("app.services.aof_growth_hub.build_checkout_caption_line", return_value="")
@patch("app.services.aof_growth_hub.resolve_group_access_plan_id", return_value=10)
def test_featured_spotlight_mentions_mainhub(_plan, _checkout):
    db = MagicMock()
    lv = {"milf": "https://gate.example/milf"}
    html = build_liveness_featured_spotlight(db, lv, "\nFOOTER", network_key="milf")
    assert "CHANNEL OF THE DAY" in html
    assert "aofmainhub" in html
    assert "mature curves" in html.lower() or "MILF" in html
    assert "FOOTER" in html


def test_featured_drop_ticker_mentions_lane_and_hub():
    html = build_liveness_featured_drop_ticker(MagicMock(), "\nF", network_key="ass")
    assert "Today's lane" in html
    assert "aofmainhub" in html
    assert "F" in html


def test_align_enabled_by_default():
    with patch.dict("os.environ", {}, clear=False):
        assert lane_of_day_align_enabled() is True
