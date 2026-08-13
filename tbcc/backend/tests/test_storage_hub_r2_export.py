"""Unit tests for Storage Hub → R2 export helpers (no Telethon/R2 I/O)."""

from __future__ import annotations

import json
from types import SimpleNamespace

from app.services.storage_hub_r2_export import (
    media_has_r2,
    media_r2_export_skipped,
    object_key_for_media,
    r2_meta_from_media,
    _is_telegram_missing_error,
)


def test_r2_meta_from_media_roundtrip():
    media = SimpleNamespace(
        classification_json=json.dumps(
            {"r2": {"object_key": "library/hub/1/abc.jpg", "direct_url": "https://cdn.example/x"}}
        )
    )
    meta = r2_meta_from_media(media)
    assert meta is not None
    assert meta["object_key"] == "library/hub/1/abc.jpg"
    assert media_has_r2(media) is True


def test_r2_meta_missing():
    media = SimpleNamespace(classification_json=None)
    assert r2_meta_from_media(media) is None
    assert media_has_r2(media) is False


def test_object_key_for_media():
    media = SimpleNamespace(id=42, file_unique_id="abc/def", media_type="video")
    key = object_key_for_media(media, content_type="video/mp4")
    assert key.startswith("library/hub/42/")
    assert key.endswith(".mp4")


def test_media_r2_export_skipped():
    media = SimpleNamespace(
        classification_json=json.dumps(
            {"r2_export_skip": {"reason": "telegram_404", "detail": "404: Media not found in Telegram"}}
        )
    )
    assert media_r2_export_skipped(media) is True
    assert media_has_r2(media) is False


def test_is_telegram_missing_error():
    assert _is_telegram_missing_error(Exception("404: Media not found in Telegram")) is True
    assert _is_telegram_missing_error(Exception("timeout")) is False
