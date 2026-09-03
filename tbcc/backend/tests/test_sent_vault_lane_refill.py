"""SENT VAULT dry-lane recycle."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.data.aof_storage_hub_map import category_emoji_for_network_key
from app.services.sent_vault_lane_refill import (
    SENT_VAULT_RECYCLE_SKIP_KEYS,
    _sample_vault_buckets,
    approve_media_from_vault_message,
    build_loot_sent_vault_refill_plan,
    lane_key_from_vault_caption,
    network_key_for_pool_name,
    vault_caption_matches_lane,
)
from app.services.storage_sent_cache import sent_cache_caption


def test_vault_caption_matches_big_tits():
    cap = sent_cache_caption("big_tits")
    assert vault_caption_matches_lane(cap, "big_tits")
    assert not vault_caption_matches_lane(cap, "blowjob")


def test_lane_key_from_vault_caption_tag():
    cap = "✅🍒 #tbcc:big_tits"
    assert lane_key_from_vault_caption(cap, {"big_tits", "ass"}) == "big_tits"


def test_lane_key_from_vault_caption_emoji_only():
    emoji = category_emoji_for_network_key("ass")
    cap = f"✅{emoji}"
    assert lane_key_from_vault_caption(cap, {"ass", "milf"}) == "ass"


def test_skip_keys_include_loot_and_full_length():
    assert "main" in SENT_VAULT_RECYCLE_SKIP_KEYS
    assert "full_length" in SENT_VAULT_RECYCLE_SKIP_KEYS
    assert "blowjob" not in SENT_VAULT_RECYCLE_SKIP_KEYS


def test_network_key_for_pool_name():
    assert network_key_for_pool_name("AOF BLOWJOB POOL") == "blowjob"
    assert network_key_for_pool_name("AOF LOOT ROOM POOL") == "main"
    assert network_key_for_pool_name("UNKNOWN") is None


def test_sample_vault_buckets_randomizes_not_sequential():
    msgs = [SimpleNamespace(id=i) for i in range(10)]
    buckets = {"blowjob": list(msgs)}
    with patch("app.services.sent_vault_lane_refill.random.shuffle") as shuffle:
        picked = _sample_vault_buckets(buckets, {"blowjob": 2})
        shuffle.assert_called_once()
    assert len(picked["blowjob"]) == 2
    assert {m.id for m in picked["blowjob"]}.issubset({m.id for m in msgs})


def test_approve_media_from_vault_message_creates_row(db):
    from app.models.content_pool import ContentPool
    from app.models.media import Media
    from telethon.tl.types import MessageMediaPhoto

    pool = ContentPool(name="TEST POOL", channel_id=1)
    db.add(pool)
    db.commit()

    msg = SimpleNamespace(id=9001, media=MessageMediaPhoto(photo=SimpleNamespace(id=111)))

    row = approve_media_from_vault_message(db, msg, pool_id=int(pool.id), network_key="big_tits")
    assert row is not None
    assert row.status == "approved"
    assert row.telegram_message_id == 9001
    assert "sent_vault_recycled" in (row.tags or "")

    again = approve_media_from_vault_message(db, msg, pool_id=int(pool.id), network_key="big_tits")
    assert again is None
    assert db.query(Media).filter(Media.pool_id == pool.id).count() == 1


def test_approve_media_revives_posted_row(db):
    from app.models.content_pool import ContentPool
    from app.models.media import Media
    from telethon.tl.types import MessageMediaPhoto

    pool = ContentPool(name="REVIVE POOL", channel_id=2)
    db.add(pool)
    db.commit()
    old = Media(
        telegram_message_id=1,
        file_id="222",
        file_unique_id="222",
        media_type="photo",
        source_channel="me",
        pool_id=int(pool.id),
        status="posted",
    )
    db.add(old)
    db.commit()

    msg = SimpleNamespace(id=9002, media=MessageMediaPhoto(photo=SimpleNamespace(id=222)))
    row = approve_media_from_vault_message(db, msg, pool_id=int(pool.id), network_key="milf")
    assert row is not None
    assert row.id == old.id
    assert row.status == "approved"
    assert row.telegram_message_id == 9002


def test_loot_vault_plan_fills_loot_room_from_content_lanes(db):
    from app.models.content_pool import ContentPool

    pool = ContentPool(name="AOF LOOT ROOM POOL", channel_id=99)
    db.add(pool)
    db.commit()

    plan = build_loot_sent_vault_refill_plan(db, [int(pool.id)], need=6)
    assert plan
    assert "main" not in plan
    assert any(entry.pool_id == int(pool.id) for entry in plan.values())
    assert "blowjob" in plan or "ass" in plan or "big_tits" in plan
    for key in plan:
        assert key not in SENT_VAULT_RECYCLE_SKIP_KEYS

