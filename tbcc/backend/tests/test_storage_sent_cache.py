"""SENT CACHE caption stamps after /deposit."""

from app.data.aof_storage_hub_map import category_emoji_for_network_key
from app.services.storage_sent_cache import sent_cache_caption


def test_sent_cache_caption_big_tits():
    assert sent_cache_caption("big_tits") == "✅🍒 #tbcc:big_tits"


def test_sent_cache_caption_blowjob():
    assert sent_cache_caption("blowjob") == "✅💋 #tbcc:blowjob"


def test_sent_cache_caption_voyeur():
    assert sent_cache_caption("voyeur") == "✅👀 #tbcc:voyeur"


def test_category_emoji_fallback():
    assert category_emoji_for_network_key("unknown_lane") == "📁"
