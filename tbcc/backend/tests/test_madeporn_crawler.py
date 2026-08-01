"""made.porn crawler URL extraction and mp4 variant dedupe."""

from app.services.crawler_resolver import (
    _dedupe_madeporn_mp4_urls,
    _extract_madeporn_media_urls,
    _is_madeporn_url,
    _madeporn_mp4_group_key,
)

SAMPLE_GALLERY_HTML = """
<html><body>
<meta property="og:video" content="https://made.porn/vs/Wg/GT/EqQ0qLlGTWg-TwXhHYXtUgY_av1.mp4">
<a href="/v/QnkIqvRUWor"><img src="https://made.porn/600/is/LO/0l/SmNJiUq0lLO-PmJu7o9Gvef.jpg"></a>
<script>
var x = "https://made.porn/vs/or/UW/QnkIqvRUWor-Ne51UDjT4hD_avc.mp4";
var y = "https://made.porn/vs/or/UW/QnkIqvRUWor-Ne51UDjT4hD_av1.mp4";
</script>
<img src="https://made.porn/is/fM/4l/N73XU4h4lfM-IvaT9WoWllc.jpg">
</body></html>
"""


def test_is_madeporn_url():
    assert _is_madeporn_url("https://made.porn/v/EqQ0qLlGTWg")
    assert _is_madeporn_url("https://www.made.porn/")
    assert not _is_madeporn_url("https://erome.com/a/x")


def test_madeporn_mp4_dedupe_prefers_avc():
    av1 = "https://made.porn/vs/Wg/GT/EqQ0qLlGTWg-TwXhHYXtUgY_av1.mp4"
    avc = "https://made.porn/vs/Wg/GT/EqQ0qLlGTWg-TwXhHYXtUgY_avc.mp4"
    assert _madeporn_mp4_group_key(av1) == _madeporn_mp4_group_key(avc)
    out = _dedupe_madeporn_mp4_urls([av1, avc])
    assert out == [avc]


def test_extract_madeporn_media_urls():
    mp4s, images = _extract_madeporn_media_urls(SAMPLE_GALLERY_HTML)
    assert len(mp4s) == 2
    assert any("QnkIqvRUWor" in u and u.endswith("_avc.mp4") for u in mp4s)
    assert any("EqQ0qLlGTWg" in u for u in mp4s)
    assert len(images) == 1
    assert images[0].endswith(".jpg")
