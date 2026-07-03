"""Post scheduler: pool interval + scheduled post enqueue rules."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.services.post_scheduler import (
    check_and_schedule,
    pool_auto_post_enabled,
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
    db.query.return_value.all.return_value = [pool]
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
    db.query.side_effect = [pool_q, ch_q]
    now = datetime.utcnow()
    with patch("app.services.post_scheduler.pool_auto_post_enabled", return_value=True):
        with patch("app.services.post_scheduler.pool_autopost_pause_when_overdue", return_value=False):
            with patch("app.services.post_scheduler.pool_queue_length", return_value=0):
                with patch("app.services.post_scheduler.post_pool") as delay:
                    _schedule_pool_interval_posts(db, now)
                    delay.delay.assert_called_once_with(7, "@testch")
                    assert pool.last_posted == now


def test_pool_autopost_skipped_when_any_scheduler_overdue():
    db = MagicMock()
    pool = MagicMock()
    pool.id = 7
    pool.auto_post_enabled = True
    pool.interval_minutes = 60
    pool.last_posted = None
    pool.channel_id = 1
    db.query.return_value.all.return_value = [pool]
    with patch("app.services.post_scheduler.pool_auto_post_enabled", return_value=True):
        with patch("app.services.post_scheduler.pool_autopost_pause_when_overdue", return_value=True):
            with patch(
                "app.services.post_scheduler.count_overdue_scheduled_posts",
                return_value=[{"id": 1}],
            ):
                with patch("app.services.post_scheduler.post_pool") as delay:
                    _schedule_pool_interval_posts(db, datetime.utcnow())
                    delay.delay.assert_not_called()


def test_check_and_schedule_commits():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    with patch("app.services.post_scheduler._schedule_pool_interval_posts"):
        check_and_schedule(db)
    db.commit.assert_called_once()
