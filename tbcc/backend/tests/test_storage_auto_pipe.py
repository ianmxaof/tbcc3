"""Tests for auto-pipe + quarantine batch review."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.data.aof_storage_hub_map import GATEKEEPER_REVIEW_TOPIC_ID
from app.services.quarantine_batch_review import (
    format_batch_caption,
    parse_batch_review_callback,
    review_batch_size,
)
from app.services.storage_auto_pipe import (
    auto_pipe_debounce_s,
    lane_auto_pipe_enabled,
    set_storage_auto_pipe_enabled,
    signal_lane_auto_pipe,
    storage_auto_pipe_enabled,
)


def test_gatekeeper_review_topic_default_is_one():
    assert GATEKEEPER_REVIEW_TOPIC_ID == 1


def test_review_batch_size_default():
    assert review_batch_size() == 10


def test_batch_review_callback_parse():
    assert parse_batch_review_callback("gk:ba:abcd1234") == ("approve", "abcd1234")
    assert parse_batch_review_callback("gk:br:abcd1234") == ("reject", "abcd1234")


def test_storage_auto_pipe_enabled_by_default():
    assert storage_auto_pipe_enabled() is True


def test_storage_auto_pipe_toggle_redis(monkeypatch):
    fake = MagicMock()
    store: dict[str, str] = {}

    def _get(key):
        return store.get(key)

    def _set(key, val, ex=None):
        store[key] = val

    fake.get.side_effect = _get
    fake.set.side_effect = _set
    monkeypatch.setattr("app.services.storage_auto_pipe._redis", lambda: fake)

    set_storage_auto_pipe_enabled(False)
    assert storage_auto_pipe_enabled() is False
    set_storage_auto_pipe_enabled(True)
    assert storage_auto_pipe_enabled() is True


def test_lane_auto_pipe_enabled_for_content_lane():
    assert lane_auto_pipe_enabled("milf") is True
    assert lane_auto_pipe_enabled("packs") is False


def test_format_batch_caption_numbered_lines():
    class _Media:
        def __init__(self, mid: int):
            self.id = mid
            self.pool_id = 1
            self.source_channel = "telegram:-1003812457581#topic:5972"
            self.classification_json = '{"gatekeeper":{"quality_score":52}}'

    db = MagicMock()
    with patch("app.services.quarantine_batch_review.resolve_media_lane_key", return_value="milf"):
        text = format_batch_caption(
            db,
            [_Media(120), _Media(121)],
            batch_id="abc",
            label="Q&A",
            lane_key="milf",
        )
    assert "0120" in text
    assert "0121" in text
    assert "MILF" in text


def test_signal_lane_auto_pipe_schedules_once(monkeypatch):
    fake = MagicMock()
    store: dict[str, str] = {}

    def _get(key):
        return store.get(key)

    def _set(key, val, ex=None):
        store[key] = val

    fake.get.side_effect = _get
    fake.set.side_effect = _set
    monkeypatch.setattr("app.services.storage_auto_pipe._redis", lambda: fake)
    monkeypatch.setattr("app.services.storage_auto_pipe.storage_auto_pipe_enabled", lambda: True)
    monkeypatch.setattr("app.services.storage_auto_pipe.lane_auto_pipe_enabled", lambda _k: True)

    calls = []
    monkeypatch.setattr(
        "app.workers.storage_auto_pipe_worker.run_lane_auto_pipe_task.apply_async",
        lambda *a, **k: calls.append(k) or MagicMock(),
    )

    out1 = signal_lane_auto_pipe("milf", 5972)
    out2 = signal_lane_auto_pipe("milf", 5972)
    assert out1.get("scheduled") is True
    assert out2.get("scheduled") is False
    assert len(calls) == 1
    assert calls[0].get("countdown") == auto_pipe_debounce_s()
