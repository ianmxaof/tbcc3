"""Post scheduler: pool interval + scheduled post enqueue rules."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.services.post_scheduler import (
    check_and_schedule,
    next_slot_stamp,
    pool_auto_post_enabled,
    recurring_slot_slippage_seconds,
    sched_max_catchup_slots,
    _schedule_pool_interval_posts,
)


def test_pool_auto_post_enabled_default():
    with patch.dict("os.environ", {}, clear=False):
        assert pool_auto_post_enabled() is True


def test_pool_auto_post_disabled_env():
    with patch.dict("os.environ", {"TBCC_POOL_AUTO_POST": "0"}, clear=False):
        assert pool_auto_post_enabled() is False


def test_schedule_pool_skips_when_auto_post_disabled():
    db = MagicMock()
    pool = MagicMock()
    pool.auto_post_enabled = True
    pool.interval_minutes = 60
    pool.last_posted = None
    pool.channel_id = 1
    pool.id = 1
    pool_q = MagicMock()
    pool_q.all.return_value = [pool]
    sched_q = MagicMock()
    sched_q.filter.return_value.first.return_value = None
    db.query.side_effect = [pool_q, sched_q]
    with patch("app.services.post_scheduler.pool_auto_post_enabled", return_value=False):
        with patch("app.services.post_scheduler.post_pool") as delay:
            _schedule_pool_interval_posts(db, datetime.utcnow())
            delay.delay.assert_not_called()


def test_schedule_pool_enqueues_when_due():
    db = MagicMock()
    pool = MagicMock()
    pool.auto_post_enabled = True
    pool.interval_minutes = 60
    pool.last_posted = datetime.utcnow() - timedelta(hours=2)
    pool.channel_id = 1
    pool.id = 7
    channel = MagicMock()
    channel.identifier = "@testch"
    pool_q = MagicMock()
    pool_q.all.return_value = [pool]
    ch_q = MagicMock()
    ch_q.filter.return_value.first.return_value = channel
    sched_q = MagicMock()
    sched_q.filter.return_value.first.return_value = None
    db.query.side_effect = [pool_q, sched_q, ch_q]
    now = datetime.utcnow()
    with patch("app.services.post_scheduler.pool_auto_post_enabled", return_value=True):
        with patch("app.services.post_scheduler.pool_autopost_pause_when_overdue", return_value=False):
            with patch("app.services.post_scheduler.pool_queue_length", return_value=0):
                with patch("app.services.post_scheduler.post_pool") as delay:
                    _schedule_pool_interval_posts(db, now)
                    delay.delay.assert_called_once_with(7, "@testch")
                    assert pool.last_posted == now


def test_pool_autopost_skipped_when_pool_has_recurring_scheduler():
    db = MagicMock()
    pool = MagicMock()
    pool.auto_post_enabled = True
    pool.interval_minutes = 60
    pool.last_posted = None
    pool.channel_id = 1
    pool.id = 7
    pool_q = MagicMock()
    pool_q.all.return_value = [pool]
    sched_q = MagicMock()
    sched_q.filter.return_value.first.return_value = (99,)
    db.query.side_effect = [pool_q, sched_q]
    with patch("app.services.post_scheduler.pool_auto_post_enabled", return_value=True):
        with patch("app.services.post_scheduler.pool_autopost_pause_when_overdue", return_value=False):
            with patch("app.services.post_scheduler.post_pool") as delay:
                _schedule_pool_interval_posts(db, datetime.utcnow())
                delay.delay.assert_not_called()


def test_pool_autopost_skipped_when_any_scheduler_overdue():
    db = MagicMock()
    pool = MagicMock()
    pool.id = 7
    pool.auto_post_enabled = True
    pool.interval_minutes = 60
    pool.last_posted = None
    pool.channel_id = 1
    pool_q = MagicMock()
    pool_q.all.return_value = [pool]
    sched_q = MagicMock()
    sched_q.filter.return_value.first.return_value = None
    db.query.side_effect = [pool_q, sched_q]
    with patch("app.services.post_scheduler.pool_auto_post_enabled", return_value=True):
        with patch("app.services.post_scheduler.pool_autopost_pause_when_overdue", return_value=True):
            with patch(
                "app.services.post_scheduler.count_overdue_scheduled_posts",
                return_value=[{"id": 1}],
            ):
                with patch("app.services.post_scheduler.post_pool") as delay:
                    _schedule_pool_interval_posts(db, datetime.utcnow())
                    delay.delay.assert_not_called()


def test_ensure_scheduled_drain_spawns_when_stale_tick():
    from app.services.post_scheduler import ensure_scheduled_drain_running

    with patch("app.services.post_scheduler.scheduler_queue_length", return_value=0):
        with patch("app.services.post_scheduler.release_post_drain_tick_lock") as release:
            with patch("app.services.post_scheduler._post_drain_tick_ttl_s", return_value=600):
                mock_r = MagicMock()
                mock_r.llen.return_value = 3
                mock_r.get.return_value = b"1"
                mock_r.set.return_value = True
                with patch("redis.from_url", return_value=mock_r):
                    with patch(
                        "app.workers.poster_worker.drain_scheduled_post_queue"
                    ) as drain:
                        out = ensure_scheduled_drain_running()
    release.assert_called_once()
    drain.delay.assert_called_once()
    assert out["action"] == "spawn_drain"


def test_ensure_scheduled_drain_none_when_empty():
    with patch("app.services.post_scheduler.scheduler_queue_length", return_value=0):
        mock_r = MagicMock()
        mock_r.llen.return_value = 0
        with patch("redis.from_url", return_value=mock_r):
            from app.services.post_scheduler import ensure_scheduled_drain_running

            out = ensure_scheduled_drain_running()
    assert out["action"] == "none"


def test_check_and_schedule_commits():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    with patch("app.services.post_scheduler._schedule_pool_interval_posts"):
        check_and_schedule(db)
    db.commit.assert_called_once()


def test_recurring_slot_slippage_seconds_on_time():
    post = MagicMock()
    post.interval_minutes = 60
    post.last_posted_at = datetime(2026, 1, 1, 12, 0, 0)
    stamped_at = datetime(2026, 1, 1, 13, 0, 0)
    assert recurring_slot_slippage_seconds(post, stamped_at) == 0.0


def test_recurring_slot_slippage_seconds_late():
    post = MagicMock()
    post.interval_minutes = 60
    post.last_posted_at = datetime(2026, 1, 1, 12, 0, 0)
    stamped_at = datetime(2026, 1, 1, 13, 2, 30)
    assert recurring_slot_slippage_seconds(post, stamped_at) == 150.0


def test_recurring_slot_slippage_seconds_first_run_none():
    post = MagicMock()
    post.interval_minutes = 60
    post.last_posted_at = None
    assert recurring_slot_slippage_seconds(post, datetime.utcnow()) is None


def test_recurring_slot_slippage_seconds_non_recurring_none():
    post = MagicMock()
    post.interval_minutes = None
    post.last_posted_at = datetime(2026, 1, 1, 12, 0, 0)
    assert recurring_slot_slippage_seconds(post, datetime.utcnow()) is None


def test_next_slot_stamp_first_run_uses_sent_at():
    post = MagicMock()
    post.interval_minutes = 60
    post.last_posted_at = None
    sent = datetime(2026, 1, 1, 12, 7, 0)
    assert next_slot_stamp(post, sent) == sent


def test_next_slot_stamp_on_time_uses_due_slot():
    post = MagicMock()
    post.interval_minutes = 60
    post.last_posted_at = datetime(2026, 1, 1, 12, 0, 0)
    sent = datetime(2026, 1, 1, 13, 2, 30)
    assert next_slot_stamp(post, sent) == datetime(2026, 1, 1, 13, 0, 0)


def test_next_slot_stamp_late_clamped_catchup():
    post = MagicMock()
    post.interval_minutes = 60
    post.last_posted_at = datetime(2026, 1, 1, 12, 0, 0)
    sent = datetime(2026, 1, 1, 15, 30, 0)
    with patch.dict("os.environ", {"TBCC_SCHED_MAX_CATCHUP_SLOTS": "1"}, clear=False):
        assert next_slot_stamp(post, sent) == datetime(2026, 1, 1, 13, 0, 0)


def test_next_slot_stamp_late_higher_catchup():
    post = MagicMock()
    post.interval_minutes = 60
    post.last_posted_at = datetime(2026, 1, 1, 12, 0, 0)
    sent = datetime(2026, 1, 1, 15, 30, 0)
    with patch.dict("os.environ", {"TBCC_SCHED_MAX_CATCHUP_SLOTS": "3"}, clear=False):
        assert next_slot_stamp(post, sent) == datetime(2026, 1, 1, 15, 0, 0)


def test_sched_max_catchup_slots_default():
    with patch.dict("os.environ", {}, clear=False):
        assert sched_max_catchup_slots() == 1
