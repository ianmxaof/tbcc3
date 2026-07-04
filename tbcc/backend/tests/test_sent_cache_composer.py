"""Tests for SENT CACHE album composer helpers."""

from app.services.cache_album_caption import _snippet_lane_keys
from app.services.sent_cache_composer import _chunk_media_rows, cache_album_size


class _FakeMedia:
    def __init__(self, mid: int, media_type: str = "video"):
        self.id = mid
        self.media_type = media_type


def test_cache_album_size_default():
    assert cache_album_size() >= 2


def test_chunk_media_rows_full_albums_only():
    rows = [_FakeMedia(i) for i in range(12)]
    albums = _chunk_media_rows(rows, 5)
    assert len(albums) == 2
    assert len(albums[0]) == 5
    assert len(albums[1]) == 5


def test_snippet_lane_keys_includes_network():
    keys = _snippet_lane_keys("big_tits")
    assert "big_tits" in keys
    assert "main_group_pulse" in keys
