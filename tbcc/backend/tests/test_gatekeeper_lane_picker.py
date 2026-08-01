"""Tests for hub-forward dedupe and gatekeeper lane picker."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.gatekeeper_lane_picker import (
    gatekeeper_lane_picker_keys,
    review_lane_picker_keyboard,
    set_picked_lanes,
    toggle_picked_lane,
)
from app.services.gatekeeper_review import parse_review_callback, review_inline_keyboard
from app.services.scrape_hub_forward_dedupe import (
    hub_forward_redis_key,
    is_hub_forward_duplicate,
    mark_hub_forward_done,
)


def test_hub_forward_redis_key_format():
    assert hub_forward_redis_key(22569, -100111, 42) == "tbcc:hub_fwd:22569:-100111:42"


def test_hub_forward_dedupe_roundtrip(monkeypatch):
    store: dict[str, str] = {}

    class FakeRedis:
        def get(self, key):
            return store.get(key)

        def set(self, key, val, ex=None):
            store[key] = val

    monkeypatch.setattr("app.services.scrape_hub_forward_dedupe._redis", lambda: FakeRedis())
    assert is_hub_forward_duplicate(22569, -100111, 99) is False
    mark_hub_forward_done(22569, -100111, 99)
    assert is_hub_forward_duplicate(22569, -100111, 99) is True


def test_parse_review_callback_toggle_lane():
    assert parse_review_callback("gk:t:42:bop") == ("toggle_lane", 42, "bop")


def test_lane_picker_keyboard_has_toggle_and_approve():
    kb = review_lane_picker_keyboard(99, selected=["bop", "ass"])
    flat = [b for row in kb["inline_keyboard"] for b in row]
    callbacks = [b["callback_data"] for b in flat]
    assert "gk:t:99:bop" in callbacks
    assert "gk:a:99" in callbacks
    assert "gk:r:99" in callbacks
    bop_btn = next(b for b in flat if b["callback_data"] == "gk:t:99:bop")
    assert bop_btn["text"].startswith("✅")


def test_toggle_picked_lane(monkeypatch):
    picked: dict[str, str] = {}

    class FakeRedis:
        def get(self, key):
            return picked.get(key)

        def set(self, key, val, ex=None):
            picked[key] = val

        def delete(self, key):
            picked.pop(key, None)

    monkeypatch.setattr("app.services.gatekeeper_lane_picker._redis", lambda: FakeRedis())
    assert toggle_picked_lane(7, "bop") == ["bop"]
    assert toggle_picked_lane(7, "bop") == []
    assert set_picked_lanes(7, ["ass", "milf"]) == ["ass", "milf"]


def test_review_inline_keyboard_uses_lane_picker_when_enabled(monkeypatch):
    monkeypatch.setenv("TBCC_GATEKEEPER_LANE_PICKER", "1")
    kb = review_inline_keyboard(5)
    flat = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    assert any(x.startswith("gk:t:5:") for x in flat)
    assert "inbox" not in gatekeeper_lane_picker_keys()
