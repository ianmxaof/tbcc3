"""Tests for Telegram → Erome storage lane."""

from __future__ import annotations

import pytest

from app.services import erome_telegram_ingest as ingest


def test_erome_storage_topic_from_env(monkeypatch):
    monkeypatch.setenv("TBCC_EROME_STORAGE_TOPIC_ID", "99999")
    assert ingest.erome_storage_topic_id() == 99999
    assert ingest.is_erome_storage_topic(99999) is True
    assert ingest.is_erome_storage_topic(1) is False


def test_erome_auto_upload_default_on(monkeypatch):
    monkeypatch.delenv("TBCC_EROME_AUTO_UPLOAD", raising=False)
    assert ingest.erome_auto_upload_enabled() is True
    monkeypatch.setenv("TBCC_EROME_AUTO_UPLOAD", "0")
    assert ingest.erome_auto_upload_enabled() is False


def test_format_erome_upload_reply_ok():
    text = ingest.format_erome_upload_reply(
        {"ok": True, "album_url": "https://www.erome.com/a/abc", "title": "Teaser", "file_count": 3},
        html=False,
    )
    assert "erome.com/a/abc" in text
    assert "3" in text
