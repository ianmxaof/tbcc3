"""Tests for chained deposit mirror task."""

from app.workers.topic_mirror_worker import (
    mirror_after_channel_import,
    mirror_after_deposit_job,
)


def test_mirror_after_import_skips_when_nothing_stored(monkeypatch):
    monkeypatch.setattr(
        "app.services.aof_topic_mirror.topic_mirror_enabled",
        lambda: True,
    )
    out = mirror_after_channel_import(
        {"ok": True, "stored": 0, "job_id": "x"},
        1,
        2,
        limit=5,
        media_types="both",
    )
    assert out.get("skipped") is True
    assert out.get("reason") == "nothing_stored"


def test_mirror_after_import_skips_when_import_failed(monkeypatch):
    monkeypatch.setattr(
        "app.services.aof_topic_mirror.topic_mirror_enabled",
        lambda: True,
    )
    out = mirror_after_channel_import(
        {"ok": False, "error": "session busy"},
        1,
        2,
    )
    assert out.get("skipped") is True
    assert out.get("reason") == "import_failed"


def test_mirror_after_deposit_job_skips_when_import_stored_zero(monkeypatch):
    monkeypatch.setattr(
        "app.workers.topic_mirror_worker._wait_import_job_terminal_sync",
        lambda _jid: {"status": "done", "result": {"stored": 0}},
    )
    monkeypatch.setattr(
        "app.services.aof_topic_mirror.topic_mirror_enabled",
        lambda: True,
    )
    out = mirror_after_deposit_job("job-1", 1, 2)
    assert out.get("skipped") is True
    assert out.get("reason") == "nothing_stored"
