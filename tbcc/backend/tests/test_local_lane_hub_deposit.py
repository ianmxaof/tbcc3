"""Tests for local lane → Storage Hub deposit mapping and ledger."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services import local_lane_hub_ledger as ledger
from app.services.local_lane_hub_deposit import (
    _chunk_paths_for_batch,
    deposit_local_file,
    deposit_local_files_batch,
)
from app.services.local_lane_hub_map import LaneWatchTarget, lane_watch_targets, resolve_lane_for_path


def test_lane_watch_targets_include_ass(monkeypatch, tmp_path: Path):
    lib = tmp_path / "AOF NETWORK"
    (lib / "AOF ASS").mkdir(parents=True)
    monkeypatch.setenv("TBCC_WATCH_LIBRARY", str(lib))
    monkeypatch.setenv("TBCC_LOCAL_LANE_HUB_LANES", "ass")

    targets = lane_watch_targets()
    assert len(targets) == 1
    assert targets[0].network_key == "ass"
    assert targets[0].folder_name == "AOF ASS"
    assert targets[0].message_thread_id == 3779


def test_resolve_lane_for_path(monkeypatch, tmp_path: Path):
    lib = tmp_path / "AOF NETWORK"
    ass_dir = lib / "AOF ASS"
    ass_dir.mkdir(parents=True)
    file_path = ass_dir / "clip.mp4"
    file_path.write_bytes(b"fake")

    monkeypatch.setenv("TBCC_WATCH_LIBRARY", str(lib))
    monkeypatch.setenv("TBCC_LOCAL_LANE_HUB_LANES", "ass")

    target = resolve_lane_for_path(file_path)
    assert target is not None
    assert target.network_key == "ass"
    assert target.message_thread_id == 3779


def test_ledger_dedupe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "ledger.db"
    monkeypatch.setattr(ledger, "_ledger_path", lambda: db_path)

    assert ledger.is_uploaded("abc123") is False
    ledger.record_upload(
        content_sha256="abc123",
        network_key="ass",
        message_thread_id=3779,
        source_path=tmp_path / "x.mp4",
        file_size=100,
    )
    assert ledger.is_uploaded("abc123") is True
    stats = ledger.ledger_stats()
    assert stats["total_uploads"] == 1
    assert stats["by_lane"]["ass"] == 1


def test_deposit_skips_sidecar_and_non_media(monkeypatch, tmp_path: Path):
    lib = tmp_path / "AOF NETWORK"
    ass_dir = lib / "AOF ASS"
    ass_dir.mkdir(parents=True)
    sidecar = ass_dir / "clip.tbcc-meta.json"
    sidecar.write_text("{}", encoding="utf-8")
    doc = ass_dir / "notes.txt"
    doc.write_text("hi", encoding="utf-8")

    monkeypatch.setenv("TBCC_WATCH_LIBRARY", str(lib))
    monkeypatch.setenv("TBCC_LOCAL_LANE_HUB_LANES", "ass")

    ok1, msg1, _ = deposit_local_file(sidecar, dry_run=True)
    assert ok1 is False
    assert msg1 == "sidecar"

    ok2, msg2, _ = deposit_local_file(doc, dry_run=True)
    assert ok2 is False
    assert msg2 == "non_media"


def test_deposit_dry_run(monkeypatch, tmp_path: Path):
    lib = tmp_path / "AOF NETWORK"
    ass_dir = lib / "AOF ASS"
    ass_dir.mkdir(parents=True)
    media = ass_dir / "AOF_test_00001_telegram.me_aofmainhub.jpg"
    media.write_bytes(b"\xff\xd8\xff\xe0" + b"x" * 64)

    monkeypatch.setenv("TBCC_WATCH_LIBRARY", str(lib))
    monkeypatch.setenv("TBCC_LOCAL_LANE_HUB_LANES", "ass")
    monkeypatch.setattr(ledger, "_ledger_path", lambda: tmp_path / "ledger.db")

    target = LaneWatchTarget(
        network_key="ass",
        folder_name="AOF ASS",
        folder_path=ass_dir,
        message_thread_id=3779,
        topic_title="AOF ASS STORAGE",
    )
    ok, msg, rec = deposit_local_file(media, dry_run=True, target=target, stable_wait_s=0)
    assert ok is True
    assert "3779" in msg
    assert rec is not None
    assert rec.get("action") == "dry_run"


class _FakeStorage:
    def __init__(self) -> None:
        self.calls = 0

    async def post_bytes_to_channel(self, channel, items, tid, caption=None, send_silent=False, skip_watermark=False, **kw):
        self.calls += 1
        return {"ok": True}


def _make_target(ass_dir: Path) -> LaneWatchTarget:
    return LaneWatchTarget(
        network_key="ass",
        folder_name="AOF ASS",
        folder_path=ass_dir,
        message_thread_id=3779,
        topic_title="AOF ASS STORAGE",
    )


def test_batch_upload_reuses_single_telethon_session(monkeypatch, tmp_path: Path):
    lib = tmp_path / "AOF NETWORK"
    ass_dir = lib / "AOF ASS"
    ass_dir.mkdir(parents=True)
    files = []
    for i in range(5):
        f = ass_dir / f"AOF_test_{i:05d}_telegram.me_aofmainhub.jpg"
        f.write_bytes(b"\xff\xd8\xff\xe0" + f"body-{i}".encode() * 8)
        files.append(f)

    monkeypatch.setenv("TBCC_WATCH_LIBRARY", str(lib))
    monkeypatch.setenv("TBCC_LOCAL_LANE_HUB_LANES", "ass")
    monkeypatch.setenv("TBCC_LOCAL_LANE_HUB_DIRECT_POST", "1")
    monkeypatch.setattr(ledger, "_ledger_path", lambda: tmp_path / "ledger.db")

    target = _make_target(ass_dir)
    storage = _FakeStorage()
    connect_calls = {"n": 0}

    async def fake_run_telegram_import_io(fn, **kw):
        connect_calls["n"] += 1
        return await fn(storage)

    import app.services.telegram_admin as telegram_admin

    monkeypatch.setattr(telegram_admin, "run_telegram_import_io", fake_run_telegram_import_io)

    results = deposit_local_files_batch(files, stable_wait_s=0, target=target)

    assert len(results) == 5
    assert all(ok for ok, _msg, _rec in results)
    assert storage.calls == 5
    # I4: one Telethon session for the whole batch, not one connect per file.
    assert connect_calls["n"] == 1


def test_deposit_reads_file_bytes_once(monkeypatch, tmp_path: Path):
    """I5: no double read — sha256 is computed from the bytes already read for upload."""
    lib = tmp_path / "AOF NETWORK"
    ass_dir = lib / "AOF ASS"
    ass_dir.mkdir(parents=True)
    media = ass_dir / "AOF_test_00001_telegram.me_aofmainhub.jpg"
    media.write_bytes(b"\xff\xd8\xff\xe0" + b"x" * 64)

    monkeypatch.setenv("TBCC_WATCH_LIBRARY", str(lib))
    monkeypatch.setenv("TBCC_LOCAL_LANE_HUB_LANES", "ass")
    monkeypatch.setattr(ledger, "_ledger_path", lambda: tmp_path / "ledger.db")

    target = _make_target(ass_dir)
    storage = _FakeStorage()

    async def fake_run_telegram_import_io(fn, **kw):
        return await fn(storage)

    import app.services.telegram_admin as telegram_admin

    monkeypatch.setattr(telegram_admin, "run_telegram_import_io", fake_run_telegram_import_io)

    read_calls = {"n": 0}
    orig_read_bytes = Path.read_bytes

    def counting_read_bytes(self):
        read_calls["n"] += 1
        return orig_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)

    ok, msg, rec = deposit_local_file(media, stable_wait_s=0, target=target)
    assert ok is True
    assert rec is not None
    assert rec.get("content_sha256")
    assert read_calls["n"] == 1


def test_chunk_paths_for_batch_respects_count_cap(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TBCC_LOCAL_LANE_HUB_BATCH_SIZE", "2")
    monkeypatch.setenv("TBCC_LOCAL_LANE_HUB_BATCH_MAX_BYTES", "1000000")
    paths = []
    for i in range(5):
        p = tmp_path / f"f{i}.jpg"
        p.write_bytes(b"x" * 10)
        paths.append(p)

    chunks = _chunk_paths_for_batch(paths)
    assert [len(c) for c in chunks] == [2, 2, 1]


def test_chunk_paths_for_batch_respects_byte_cap(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TBCC_LOCAL_LANE_HUB_BATCH_SIZE", "100")
    monkeypatch.setenv("TBCC_LOCAL_LANE_HUB_BATCH_MAX_BYTES", "1048576")
    paths = []
    for i in range(5):
        p = tmp_path / f"f{i}.jpg"
        p.write_bytes(b"x" * 400_000)
        paths.append(p)

    chunks = _chunk_paths_for_batch(paths)
    assert [len(c) for c in chunks] == [2, 2, 1]
