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


def test_sidecar_roundtrip(tmp_path: Path):
    media = tmp_path / "pic.jpg"
    media.write_bytes(b"x")
    write_watch_sidecar(media, {"tags": ["bbw"], "lane_key": "big_tits", "aof_preprocessed": True})
    side = media.with_name("pic.tbcc-meta.json")
    assert side.is_file()
    assert is_watch_sidecar_file(side)
    loaded = read_watch_sidecar(media)
    assert loaded and loaded["lane_key"] == "big_tits"
