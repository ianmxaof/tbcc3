"""Erome crawler URL classification and album link extraction."""

from app.services.crawler_resolver import (
    _classify_erome_url,
    _extract_erome_album_urls,
    _normalize_erome_album_url,
)

SAMPLE_PROFILE_HTML = """
<html><body>
<a href="/a/rdRxd7Nt" class="album-link">one</a>
<a href="https://www.erome.com/a/AbC12_x">two</a>
<a href="/search?q=x">skip</a>
</body></html>
"""


def test_classify_erome_urls():
    assert _classify_erome_url("https://www.erome.com/a/rdRxd7Nt") == "album"
    assert _classify_erome_url("https://www.erome.com/Bestvideos30?page=2") == "profile"
    assert _classify_erome_url("https://www.erome.com/search?q=goon") == "search"
    assert _classify_erome_url("https://www.erome.com/explore") == "other"


def test_extract_erome_album_urls():
    urls = _extract_erome_album_urls(SAMPLE_PROFILE_HTML)
    assert _normalize_erome_album_url("rdRxd7Nt") in urls
    assert "https://www.erome.com/a/AbC12_x" in urls
    assert len(urls) == 2
