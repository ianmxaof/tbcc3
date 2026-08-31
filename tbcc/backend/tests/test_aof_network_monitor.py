"""Tests for AOF NETWORK monitor status aggregation."""

from __future__ import annotations

from pathlib import Path

from app.services.aof_network_monitor import collect_aof_network_status


def test_collect_status_shape(monkeypatch, tmp_path: Path):
    lib = tmp_path / "AOF NETWORK"
    inbox = lib / "Google Drive Daemon" / "Inbox"
    ass = lib / "AOF ASS"
    inbox.mkdir(parents=True)
    ass.mkdir(parents=True)
    (inbox / "pending.mp4").write_bytes(b"x" * 10)
    (ass / "lane.mp4").write_bytes(b"y" * 10)

    monkeypatch.setenv("TBCC_WATCH_LIBRARY", str(lib))
    monkeypatch.setenv("TBCC_WATCH_INBOX", str(inbox))
    monkeypatch.setenv("TBCC_LOCAL_LANE_HUB_LANES", "ass")
    monkeypatch.setenv("TBCC_LOCAL_LANE_HUB_ENABLED", "1")
    monkeypatch.setattr("app.services.watch_folder_control._load_dotenv", lambda: None)
    monkeypatch.setattr("app.services.local_lane_hub_control._load_dotenv", lambda: None)

    st = collect_aof_network_status(invalidate_counts=True, fast=False)
    assert st["ok"] is True
    assert st["summary"]["inbox_pending"] == 1
    assert st["lane_hub"]["lanes"][0]["network_key"] == "ass"
    assert st["lane_hub"]["lanes"][0]["media_count"] == 1
    assert "activity" in st
    assert "watch" in st


def test_hub_pending_uploads_reflects_disk_minus_ledger(monkeypatch, tmp_path: Path):
    """I2/I3: pending must not silently go stale once files land on disk but stay unuploaded."""
    lib = tmp_path / "AOF NETWORK"
    ass = lib / "AOF ASS"
    ass.mkdir(parents=True)
    (ass / "a.jpg").write_bytes(b"a" * 10)
    (ass / "b.jpg").write_bytes(b"b" * 10)

    monkeypatch.setenv("TBCC_WATCH_LIBRARY", str(lib))
    monkeypatch.setenv("TBCC_LOCAL_LANE_HUB_LANES", "ass")
    monkeypatch.setattr("app.services.watch_folder_control._load_dotenv", lambda: None)
    monkeypatch.setattr("app.services.local_lane_hub_control._load_dotenv", lambda: None)

    from app.services import local_lane_hub_ledger as ledger

    db_path = tmp_path / "ledger.db"
    monkeypatch.setattr(ledger, "_ledger_path", lambda: db_path)
    ledger.record_upload(
        content_sha256="abc123",
        network_key="ass",
        message_thread_id=3779,
        source_path=ass / "a.jpg",
        file_size=10,
    )

    st = collect_aof_network_status(invalidate_counts=True, fast=False)
    lane = st["lane_hub"]["lanes"][0]
    assert lane["network_key"] == "ass"
    assert lane["media_count"] == 2
    assert lane["ledger_uploads"] == 1
    # 2 on disk, 1 already recorded -> exactly 1 still pending — never silently drops to 0
    # just because files remain on disk after upload (deposit never deletes the source).
    assert lane["pending_uploads"] == 1
    assert st["summary"]["hub_pending_uploads"] == 1
    assert st["summary"]["hub_uploads_total"] == 1


def test_hub_pending_uploads_never_negative(monkeypatch, tmp_path: Path):
    """Ledger can outnumber current disk count (files deleted post-upload) — clamp at 0."""
    lib = tmp_path / "AOF NETWORK"
    ass = lib / "AOF ASS"
    ass.mkdir(parents=True)
    (ass / "a.jpg").write_bytes(b"a" * 10)

    monkeypatch.setenv("TBCC_WATCH_LIBRARY", str(lib))
    monkeypatch.setenv("TBCC_LOCAL_LANE_HUB_LANES", "ass")
    monkeypatch.setattr("app.services.watch_folder_control._load_dotenv", lambda: None)
    monkeypatch.setattr("app.services.local_lane_hub_control._load_dotenv", lambda: None)

    from app.services import local_lane_hub_ledger as ledger

    db_path = tmp_path / "ledger.db"
    monkeypatch.setattr(ledger, "_ledger_path", lambda: db_path)
    for i in range(3):
        ledger.record_upload(
            content_sha256=f"hash{i}",
            network_key="ass",
            message_thread_id=3779,
            source_path=ass / f"gone{i}.jpg",
            file_size=10,
        )

    st = collect_aof_network_status(invalidate_counts=True, fast=False)
    lane = st["lane_hub"]["lanes"][0]
    assert lane["media_count"] == 1
    assert lane["ledger_uploads"] == 3
    assert lane["pending_uploads"] == 0
    assert st["summary"]["hub_pending_uploads"] == 0
