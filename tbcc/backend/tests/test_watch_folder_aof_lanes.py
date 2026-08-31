"""Watch-folder AOF lane routing (no CLIP)."""

from pathlib import Path

from app.services.watch_folder_aof import (
    aof_library_subdir,
    preprocess_inbox_media,
    resolve_lane_from_meta,
)
from app.services.watch_folder_nsfw import is_watch_sidecar_file, read_watch_sidecar, write_watch_sidecar


def test_resolve_lane_from_bbw_tags(monkeypatch):
    monkeypatch.setenv("TBCC_WATCH_AOF_FOLDER_STYLE", "emoji")
    meta = {"tags": ["bbw", "solo"], "aof_preprocessed": True}
    assert resolve_lane_from_meta(meta) == "big_tits"
    assert aof_library_subdir("Images", meta) == "🍒 AOF BIG TITS"
    assert aof_library_subdir("Videos", meta) == "🍒 AOF BIG TITS"


def test_resolve_lane_disk_style(monkeypatch):
    monkeypatch.setenv("TBCC_WATCH_AOF_FOLDER_STYLE", "disk")
    meta = {"tags": ["bbw"], "aof_preprocessed": True}
    assert aof_library_subdir("Images", meta) == "AOF BIG TITS"


def test_inbox_lane_disk_style(monkeypatch):
    monkeypatch.setenv("TBCC_WATCH_AOF_FOLDER_STYLE", "disk")
    meta = {"lane_key": "inbox", "aof_preprocessed": True}
    assert resolve_lane_from_meta(meta) == "inbox"
    assert aof_library_subdir("Videos", meta) == "AOF INBOX"


def test_resolve_lane_preferred_key(monkeypatch):
    monkeypatch.setenv("TBCC_WATCH_AOF_FOLDER_STYLE", "disk")
    meta = {"tags": ["asian"], "lane_key": "milf"}
    assert resolve_lane_from_meta(meta) == "milf"
    assert aof_library_subdir("Images", meta) == "AOF MILFGILF"


def test_unsorted_without_tags(monkeypatch):
    monkeypatch.delenv("TBCC_WATCH_AOF_LANE_FOLDERS", raising=False)
    monkeypatch.setenv("TBCC_WATCH_AOF_FOLDER_STYLE", "emoji")
    # default on → Unsorted
    assert aof_library_subdir("Images", {}) == "Unsorted"
    assert aof_library_subdir("Audio", {"tags": ["bbw"]}) is None


def test_lane_folders_off(monkeypatch):
    monkeypatch.setenv("TBCC_WATCH_AOF_LANE_FOLDERS", "0")
    assert aof_library_subdir("Images", {"tags": ["bbw"]}) is None


def test_preprocess_skips_when_marked(tmp_path: Path):
    media = tmp_path / "AOF_media_00001_telegram.me_aofmainhub.jpg"
    media.write_bytes(b"x")
    meta = {"tags": ["bbw"], "aof_preprocessed": True, "watermark_applied": True}
    out_path, out_meta = preprocess_inbox_media(media, meta)
    assert out_path == media
    assert out_meta.get("aof_preprocessed") is True
    assert out_meta.get("lane_key") == "big_tits"


def test_fast_mode_skips_watermark(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TBCC_WATCH_AOF_FAST", "1")
    media = tmp_path / "AOF_media_00002_telegram.me_aofmainhub.jpg"
    media.write_bytes(b"x")

    called = {"n": 0}

    def fake_watermark_file(path):
        called["n"] += 1
        raise AssertionError("watermark_file must not run in fast mode (I8)")

    monkeypatch.setattr("app.services.local_media_watermark.watermark_file", fake_watermark_file)

    out_path, out_meta = preprocess_inbox_media(media, {})
    assert called["n"] == 0
    assert out_meta.get("watermark_skipped") == "fast_mode"
    assert out_path.is_file()


def test_sidecar_roundtrip(tmp_path: Path):
    media = tmp_path / "pic.jpg"
    media.write_bytes(b"x")
    write_watch_sidecar(media, {"tags": ["bbw"], "lane_key": "big_tits", "aof_preprocessed": True})
    side = media.with_name("pic.tbcc-meta.json")
    assert side.is_file()
    assert is_watch_sidecar_file(side)
    loaded = read_watch_sidecar(media)
    assert loaded and loaded["lane_key"] == "big_tits"
