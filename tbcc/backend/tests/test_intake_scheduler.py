"""Tests for intake scheduler + inbox source routing."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.data.aof_storage_hub_map import INBOX_CHANNEL_IDENT, INBOX_TOPIC_ID, STORAGE_HUB_IDENT
from app.services.inbox_intake_review import is_inbox_source_label, parse_batch_review_callback
from app.services.intake_scheduler import (
    adjust_album_size,
    adjust_batch_size,
    adjust_interval_minutes,
    get_album_size,
    get_batch_size,
    get_interval_minutes,
    lane_due_for_run,
    mark_lane_run,
)


def test_is_inbox_source_label_topic_and_channel():
    assert is_inbox_source_label(f"telegram:{STORAGE_HUB_IDENT}#topic:{INBOX_TOPIC_ID}")
    assert is_inbox_source_label(f"telegram:{INBOX_CHANNEL_IDENT}")
    assert not is_inbox_source_label(f"telegram:{STORAGE_HUB_IDENT}#topic:3387")


def test_batch_review_callback_parse():
    assert parse_batch_review_callback("gk:ba:abcd1234") == ("approve", "abcd1234")
    assert parse_batch_review_callback("gk:br:abcd1234") == ("reject", "abcd1234")
    assert parse_batch_review_callback("gk:a:99") is None


def test_intake_scheduler_adjustments(monkeypatch):
    monkeypatch.setenv("TBCC_INTAKE_BATCH_SIZE", "8")
    monkeypatch.setenv("TBCC_INTAKE_INTERVAL_MIN", "60")
    monkeypatch.setenv("TBCC_INTAKE_ALBUM_SIZE", "5")

    fake = MagicMock()
    store: dict[str, str] = {}

    def _get(key):
        return store.get(key)

    def _set(key, val, ex=None):
        store[key] = val

    fake.get.side_effect = _get
    fake.set.side_effect = _set
    monkeypatch.setattr("app.services.intake_scheduler._redis", lambda: fake)

    assert adjust_batch_size(10) == 18
    assert get_batch_size() == 18
    assert adjust_interval_minutes(15) == 75
    assert get_interval_minutes() == 75
    assert adjust_album_size(2) == 7
    assert get_album_size() == 7


def test_lane_due_for_run_after_mark(monkeypatch):
    monkeypatch.setenv("TBCC_INTAKE_INTERVAL_MIN", "60")
    fake = MagicMock()
    store: dict[str, str] = {}

    def _get(key):
        return store.get(key)

    def _set(key, val, ex=None):
        store[key] = val

    fake.get.side_effect = _get
    fake.set.side_effect = _set
    monkeypatch.setattr("app.services.intake_scheduler._redis", lambda: fake)

    assert lane_due_for_run("abg", force=False) is True
    mark_lane_run("abg")
    assert lane_due_for_run("abg", force=False) is False
    assert lane_due_for_run("abg", force=True) is True
