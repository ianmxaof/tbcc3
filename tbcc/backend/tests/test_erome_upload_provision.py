"""Erome upload staging scan and album URL extraction."""

from pathlib import Path

from app.services.erome_upload_provision import (
    extract_erome_album_url,
    load_flow_config,
    scan_staging_folder,
    selectors_ready,
)


def test_extract_erome_album_url():
    assert extract_erome_album_url("https://www.erome.com/a/rdRxd7Nt") == "https://www.erome.com/a/rdRxd7Nt"
    assert extract_erome_album_url('href="https://www.erome.com/a/AbC12_x"') == "https://www.erome.com/a/AbC12_x"
    assert extract_erome_album_url("https://example.com") is None


def test_scan_staging_folder(tmp_path: Path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    (tmp_path / "b.txt").write_text("skip")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.png").write_bytes(b"y")
    scan = scan_staging_folder(tmp_path)
    assert scan.ok
    assert len(scan.files) == 2
    names = {p.name for p in scan.files}
    assert names == {"a.jpg", "c.png"}
    assert any("b.txt" in s for s in scan.skipped)


def test_selectors_ready_from_flow():
    cfg = load_flow_config()
    assert selectors_ready(cfg)
