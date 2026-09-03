"""SENT CACHE caption stamps after /deposit."""

from app.data.aof_storage_hub_map import category_emoji_for_network_key
from app.services.storage_sent_cache import _dedupe_buffer_items, sent_cache_caption


def test_sent_cache_caption_big_tits():
    assert sent_cache_caption("big_tits") == "✅🍒 #tbcc:big_tits"


def test_sent_cache_caption_blowjob():
    assert sent_cache_caption("blowjob") == "✅💋 #tbcc:blowjob"


def test_sent_cache_caption_voyeur():
    assert sent_cache_caption("voyeur") == "✅👀 #tbcc:voyeur"


def test_category_emoji_fallback():
    assert category_emoji_for_network_key("unknown_lane") == "📁"


def test_dedupe_buffer_items_keeps_first_per_media_id():
    items = [
        {"media_id": 1, "message_id": 10},
        {"media_id": 1, "message_id": 11},
        {"media_id": 2, "message_id": 20},
        {"media_id": 1, "message_id": 12},
    ]
    out = _dedupe_buffer_items(items)
    assert [r["media_id"] for r in out] == [1, 2]
    assert out[0]["message_id"] == 10
