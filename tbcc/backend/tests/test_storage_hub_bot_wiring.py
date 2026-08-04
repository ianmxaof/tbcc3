"""Tests for lane composer status + storage hub bot wiring."""

from app.services.lane_composer_status import (
    format_lane_composer_status_line,
    record_lane_composer_status,
)
from app.services.storage_hub_bot_wiring import (
    album_composer_storage_hub_enabled,
    gatekeeper_review_bot_default,
    payment_storage_hub_enabled,
)


def test_record_lane_composer_status(monkeypatch):
    store: dict[str, str] = {}

    class FakeRedis:
        def get(self, key):
            return store.get(key)

        def set(self, key, val):
            store[key] = val

    monkeypatch.setattr("app.services.lane_composer_status._redis", lambda: FakeRedis())
    record_lane_composer_status(
        "taboo",
        {"albums_built": 2, "album_size": 5, "leftover_singles": 1, "albums": []},
    )
    line = format_lane_composer_status_line("taboo")
    assert line is not None
    assert "2 × 5" in line
    assert "leftover 1" in line


def test_storage_hub_defaults_to_album_composer(monkeypatch):
    monkeypatch.delenv("TBCC_PAYMENT_STORAGE_HUB", raising=False)
    monkeypatch.delenv("TBCC_ALBUM_COMPOSER_STORAGE_HUB", raising=False)
    monkeypatch.delenv("TBCC_GATEKEEPER_REVIEW_BOT", raising=False)
    monkeypatch.setenv("TBCC_ALBUM_COMPOSER_STORAGE_DEPOSIT", "1")
    assert payment_storage_hub_enabled() is False
    assert album_composer_storage_hub_enabled() is True
    assert gatekeeper_review_bot_default() == "album_composer"
