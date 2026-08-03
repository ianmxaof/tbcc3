"""Tests for SENT CACHE album composer helpers."""

from app.services.cache_album_caption import _snippet_lane_keys
from app.services.sent_cache_composer import _chunk_media_rows, cache_album_size


class _FakeMedia:
    def __init__(self, mid: int, media_type: str = "video", tid: int = 0, fu: str = ""):
        self.id = mid
        self.media_type = media_type
        self.telegram_message_id = tid or mid
        self.file_unique_id = fu or f"fu-{mid}"


def test_cache_album_size_default():
    assert cache_album_size() >= 2


def test_chunk_media_rows_full_albums_only():
    rows = [_FakeMedia(i) for i in range(12)]
    albums = _chunk_media_rows(rows, 5)
    assert len(albums) == 2
    assert len(albums[0]) == 5
    assert len(albums[1]) == 5


def test_chunk_media_rows_dedupes_same_message_id():
    rows = [_FakeMedia(i) for i in range(1, 11)]
    for i, r in enumerate(rows):
        # Five rows share one Telegram message id (legacy sent-cache corruption pattern).
        r.telegram_message_id = 100 if i < 5 else 200 + i
        r.file_unique_id = f"fu-{r.telegram_message_id}-{i}"
    albums = _chunk_media_rows(rows, 5)
    assert len(albums) == 1
    assert len(albums[0]) == 5
    assert len({m.telegram_message_id for m in albums[0]}) == 5


def test_snippet_lane_keys_includes_network():
    keys = _snippet_lane_keys("big_tits")
    assert "big_tits" in keys
    assert "main_group_pulse" in keys
