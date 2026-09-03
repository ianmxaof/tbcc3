"""Gatekeeper quarantine callback patterns + one-tap route helpers."""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

from app.services.quarantine_batch_review import (
    CALLBACK_BATCH_TOGGLE,
    parse_batch_review_callback,
)


# Mirrors storage_hub_handlers / payment_bot registration.
_BATCH_PATTERN = re.compile(r"^gk:b(?:a|r|t):")
_SINGLE_PATTERN = re.compile(r"^gk:[atr]:")


def test_batch_callback_pattern_matches_lane_tap():
    assert _BATCH_PATTERN.match("gk:bt:9ad6d95a:voyeur")
    assert _BATCH_PATTERN.match("gk:ba:9ad6d95a")
    assert _BATCH_PATTERN.match("gk:br:9ad6d95a")
    # Legacy broken pattern must not be the only match path
    legacy = re.compile(r"^gk:b[ar]:")
    assert legacy.match("gk:bt:9ad6d95a:voyeur") is None
    assert _BATCH_PATTERN.match("gk:bt:9ad6d95a:voyeur")


def test_single_callback_pattern_matches_lane_tap():
    assert _SINGLE_PATTERN.match("gk:t:20324:voyeur")
    assert _SINGLE_PATTERN.match("gk:a:20324")
    assert _SINGLE_PATTERN.match("gk:r:20324")


def test_parse_batch_toggle_voyeur():
    assert parse_batch_review_callback(f"{CALLBACK_BATCH_TOGGLE}9ad6d95a:voyeur") == (
        "toggle_lane",
        "9ad6d95a",
        "voyeur",
    )


def test_operator_route_batch_to_lane_stamps_and_approves():
    from app.services.quarantine_batch_review import operator_route_batch_to_lane

    db = MagicMock()
    with (
        patch(
            "app.services.quarantine_batch_review.load_batch_media_ids",
            return_value=[20324],
        ),
        patch("app.services.quarantine_batch_review.fanout_batch_lane_picks") as fanout,
        patch(
            "app.services.quarantine_batch_review.operator_approve_batch",
            return_value={"ok": True, "approved": 1, "total": 1, "route_enqueue_failures": 0},
        ) as approve,
    ):
        out = operator_route_batch_to_lane(db, "abcd", "voyeur", operator_id=1)
    fanout.assert_called_once_with("abcd", ["voyeur"])
    approve.assert_called_once()
    assert out["ok"] is True
    assert out["routed_lane"] == "voyeur"


def test_vision_auto_route_is_all(monkeypatch):
    from app.services.auto_tag_enrich import vision_auto_route_is_all

    monkeypatch.delenv("TBCC_VISION_AUTO_ROUTE_LANES", raising=False)
    assert vision_auto_route_is_all() is False
    monkeypatch.setenv("TBCC_VISION_AUTO_ROUTE_LANES", "voyeur,bop")
    assert vision_auto_route_is_all() is False
    monkeypatch.setenv("TBCC_VISION_AUTO_ROUTE_LANES", "all")
    assert vision_auto_route_is_all() is True
    monkeypatch.setenv("TBCC_VISION_AUTO_ROUTE_LANES", "voyeur,ALL")
    assert vision_auto_route_is_all() is True
