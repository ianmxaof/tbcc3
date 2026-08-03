"""Tests for SENT CACHE emoji album buffer + pool schedule min-age."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.services.media_album_dedupe import (
    filter_media_older_than_schedule_min_age,
    pool_schedule_min_age_hours,
)
from app.services.sent_cache_composer import _chunk_media_rows
from app.services.storage_sent_cache import (
    _partition_by_bucket,
    _take_album_chunks,
    sent_cache_caption,
)


class _FakeMedia:
    def __init__(self, mid: int, media_type: str = "video"):
        self.id = mid
        self.media_type = media_type


def test_sent_cache_caption_uses_emoji_only():
    assert sent_cache_caption("big_tits") == "✅🍒"
    assert sent_cache_caption("ass") == "✅🍑"


def test_partition_by_bucket():
    items = [
        {"media_type": "photo", "media_id": 1},
        {"media_type": "video", "media_id": 2},
        {"media_type": "photo", "media_id": 3},
    ]
    parts = _partition_by_bucket(items)
    assert len(parts["photo"]) == 2
    assert len(parts["video"]) == 1


def test_take_album_chunks_keeps_remainder():
    items = [{"media_id": i} for i in range(7)]
    albums, left = _take_album_chunks(items, album_size=5, force=False)
    assert len(albums) == 1
    assert len(albums[0]) == 5
    assert len(left) == 2


def test_chunk_media_rows_by_lane_and_type():
    rows = [_FakeMedia(i, "photo" if i % 2 else "video") for i in range(12)]
    albums = _chunk_media_rows(rows, 5, network_key="big_tits")
    assert sum(len(a) for a in albums) == 10
    assert all(len(a) == 5 for a in albums)


def test_pool_schedule_min_age_filters_fresh(monkeypatch):
    monkeypatch.setenv("TBCC_POOL_SCHEDULE_MIN_AGE_HOURS", "24")
    assert pool_schedule_min_age_hours() == 24.0

    fresh = MagicMock()
    fresh.created_at = datetime.utcnow()
    old = MagicMock()
    old.created_at = datetime.utcnow() - timedelta(hours=30)

    kept = filter_media_older_than_schedule_min_age([fresh, old])
    assert kept == [old]
