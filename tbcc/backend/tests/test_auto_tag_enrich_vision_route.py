"""Vision-lane auto-route hook — opt-in allowlist gate on top of classify_and_log_lane_vision."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def test_disabled_by_default_when_env_unset(monkeypatch):
    from app.services.auto_tag_enrich import _maybe_auto_route_vision_lane

    monkeypatch.delenv("TBCC_VISION_AUTO_ROUTE_LANES", raising=False)
    with patch("app.services.gatekeeper_review.enqueue_lane_route_for_media") as enqueue:
        _maybe_auto_route_vision_lane(1, {"lane_key": "voyeur", "matching_lanes": ["voyeur"]})
        enqueue.assert_not_called()


def test_routes_lane_in_allowlist(monkeypatch):
    from app.services.auto_tag_enrich import _maybe_auto_route_vision_lane

    monkeypatch.setenv("TBCC_VISION_AUTO_ROUTE_LANES", "voyeur,bop")
    with patch("app.services.gatekeeper_review.enqueue_lane_route_for_media") as enqueue:
        enqueue.return_value = {"ok": True, "queued": True}
        _maybe_auto_route_vision_lane(42, {"lane_key": "voyeur", "matching_lanes": ["voyeur", "big_tits"]})
        enqueue.assert_called_once_with(42, ["voyeur"])


def test_skips_lane_not_in_allowlist(monkeypatch):
    from app.services.auto_tag_enrich import _maybe_auto_route_vision_lane

    monkeypatch.setenv("TBCC_VISION_AUTO_ROUTE_LANES", "voyeur,bop")
    with patch("app.services.gatekeeper_review.enqueue_lane_route_for_media") as enqueue:
        _maybe_auto_route_vision_lane(7, {"lane_key": "milf", "matching_lanes": ["milf"]})
        enqueue.assert_not_called()


def test_skips_when_no_lane_key():
    from app.services.auto_tag_enrich import _maybe_auto_route_vision_lane

    with patch("app.services.gatekeeper_review.enqueue_lane_route_for_media") as enqueue:
        _maybe_auto_route_vision_lane(9, {"lane_key": None, "matching_lanes": []})
        enqueue.assert_not_called()


def test_skips_when_decision_is_none():
    from app.services.auto_tag_enrich import _maybe_auto_route_vision_lane

    with patch("app.services.gatekeeper_review.enqueue_lane_route_for_media") as enqueue:
        _maybe_auto_route_vision_lane(9, None)
        enqueue.assert_not_called()


def test_enqueue_failure_does_not_raise(monkeypatch):
    from app.services.auto_tag_enrich import _maybe_auto_route_vision_lane

    monkeypatch.setenv("TBCC_VISION_AUTO_ROUTE_LANES", "voyeur")
    with patch("app.services.gatekeeper_review.enqueue_lane_route_for_media") as enqueue:
        enqueue.return_value = {"ok": False, "reason": "redis_down"}
        _maybe_auto_route_vision_lane(3, {"lane_key": "voyeur", "matching_lanes": ["voyeur"]})
        enqueue.assert_called_once()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", set()),
        ("voyeur", {"voyeur"}),
        ("voyeur,bop", {"voyeur", "bop"}),
        (" Voyeur , BOP ", {"voyeur", "bop"}),
    ],
)
def test_vision_auto_route_lanes_parsing(monkeypatch, raw, expected):
    from app.services.auto_tag_enrich import vision_auto_route_lanes

    monkeypatch.setenv("TBCC_VISION_AUTO_ROUTE_LANES", raw)
    assert vision_auto_route_lanes() == expected
