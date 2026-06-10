"""Tests for pool ↔ scheduler album setting sync."""
from types import SimpleNamespace

from app.services.pool_schedule_sync import (
    sync_pool_album_settings_to_schedules,
    sync_schedule_album_settings_to_pool,
)


def test_sync_pool_to_schedules_updates_matching_jobs():
    post = SimpleNamespace(pool_id=3, pool_collective_random=False, album_size=5, pool_randomize=False)
    db = SimpleNamespace()
    db.query.return_value.filter.return_value.all.return_value = [post]

    n = sync_pool_album_settings_to_schedules(db, 3, album_size=2, randomize_queue=True)

    assert n == 1
    assert post.album_size == 2
    assert post.pool_randomize is True


def test_sync_schedule_to_pool_updates_content_pool():
    post = SimpleNamespace(
        pool_id=4,
        pool_collective_random=False,
        album_size=3,
        pool_randomize=True,
    )
    pool = SimpleNamespace(id=4, album_size=5, randomize_queue=False)
    db = SimpleNamespace()
    db.query.return_value.filter.return_value.first.return_value = pool

    changed = sync_schedule_album_settings_to_pool(post, db)

    assert changed is True
    assert pool.album_size == 3
    assert pool.randomize_queue is True


def test_sync_schedule_skips_collective_random():
    post = SimpleNamespace(pool_id=None, pool_collective_random=True, album_size=3, pool_randomize=True)
    db = SimpleNamespace()
    assert sync_schedule_album_settings_to_pool(post, db) is False
