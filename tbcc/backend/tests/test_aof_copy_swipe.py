"""Tests for AOF copy swipe file ingest (no LLM)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from app.services import aof_copy_swipe as svc


@pytest.fixture
def temp_swipe_file(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test_swipes.json"
        monkeypatch.setattr(svc, "_SWIPES_DIR", Path(tmp))
        monkeypatch.setattr(svc, "_DEFAULT_SWIPE_FILE", "test_swipes.json")
        yield path


def test_ingest_and_list_swipe(temp_swipe_file):
    entry = svc.ingest_swipe_raw(
        "🔥 Test swipe body",
        source="test",
        tags=["library"],
        tactics=["not_a_regular_channel"],
        notes="unit test",
        swipe_id="test-swipe-1",
    )
    assert entry["id"] == "test-swipe-1"
    assert entry["raw_body"].startswith("🔥")

    again = svc.ingest_swipe_raw("🔥 Test swipe body", swipe_id="ignored")
    assert again["id"] == "test-swipe-1"

    listed = svc.list_swipes()
    assert len(listed) == 1

    data = json.loads(temp_swipe_file.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert len(data["swipes"]) == 1


def test_get_swipe_missing():
    assert svc.get_swipe("does-not-exist", "telegram_native_ads.json") is None
