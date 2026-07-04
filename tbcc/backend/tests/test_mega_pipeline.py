"""Tests for MEGA folder validation and og: meta parsing."""

from __future__ import annotations

from app.services.mega_link_extract import parse_mega_folder_page_meta
from app.services.mega_link_pipeline import _is_mega_folder, resolve_to_file_host


def test_parse_mega_folder_page_meta() -> None:
    html = """
    <title>13.73 GB folder on MEGA</title>
    <meta property="og:title" content="13.73 GB folder on MEGA" />
    <meta property="og:description" content="698 files" />
    """
    size_gb, file_count = parse_mega_folder_page_meta(html)
    assert size_gb == 13.73
    assert file_count == 698


def test_is_mega_folder_formats() -> None:
    assert _is_mega_folder("https://mega.nz/folder/abc#key")
    assert _is_mega_folder("https://mega.nz/#F!abc!key")
    assert not _is_mega_folder("https://example.com/folder/x")


def test_resolve_mega_folder_og_meta(monkeypatch) -> None:
    html = """
    <meta property="og:title" content="13.73 GB folder on MEGA" />
    <meta property="og:description" content="698 files" />
    """

    def fake_fetch(_url: str):
        return html, None

    monkeypatch.setattr("app.services.mega_link_pipeline._fetch_html", fake_fetch)
    url = "https://mega.nz/folder/urQGTZjK#6jKi9sIKcOTg6W1L4Ny8zw"
    result = resolve_to_file_host(url)
    assert result.ok is True
    assert result.size_gb_hint == 13.73
    assert result.min_rarity_tier == 8
