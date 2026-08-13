"""Celery queue purge helpers."""

from unittest.mock import MagicMock, patch

from app.services.celery_queue_ops import (
    dedupe_run_schedule_queue,
    dedupe_scrape_tick_queue,
    purge_post_pool_tasks_from_queue,
    purge_thumbnail_warm_from_telegram_queue,
)


def _broker_payload(task: str) -> str:
    import base64
    import json

    body = base64.b64encode(json.dumps([[], {}, {}]).encode()).decode()
    return json.dumps({"headers": {"task": task}, "body": body})


def test_purge_post_pool_tasks_from_queue():
    r = MagicMock()
    r.ping.return_value = True
    pool_msg = _broker_payload("app.workers.poster_worker.post_pool")
    drain_msg = _broker_payload("app.workers.poster_worker.drain_scheduled_post_queue")
    r.lrange.return_value = [pool_msg, drain_msg]
    with patch("app.services.celery_queue_ops._redis_client", return_value=r):
        out = purge_post_pool_tasks_from_queue()
    assert out["ok"] is True
    assert out["removed"] == 1
    assert out["after"] == 1
    pipe = r.pipeline.return_value
    pipe.delete.assert_called_once_with("post")
    pipe.rpush.assert_called_once()


def test_dedupe_run_schedule_keeps_newest_one():
    r = MagicMock()
    r.ping.return_value = True
    a = _broker_payload("app.workers.scheduler_worker.run_schedule")
    b = _broker_payload("app.workers.scheduler_worker.run_schedule")
    c = _broker_payload("app.workers.loot_promo_worker.send_loot_daily_promo")
    d = _broker_payload("app.workers.scheduler_worker.run_schedule")
    r.lrange.return_value = [a, b, c, d]
    with patch("app.services.celery_queue_ops._redis_client", return_value=r):
        out = dedupe_run_schedule_queue(keep=1)
    assert out["ok"] is True
    assert out["removed"] == 2
    assert out["after"] == 2  # one run_schedule + loot promo
    assert out["kept"] == 1
    pipe = r.pipeline.return_value
    pipe.delete.assert_called_once_with("celery")
    args = pipe.rpush.call_args[0]
    assert args[0] == "celery"
    assert len(args) == 3  # queue + 2 payloads


def test_dedupe_scrape_ticks_keeps_newest_one():
    r = MagicMock()
    r.ping.return_value = True
    a = _broker_payload("app.workers.scrape_scheduler_worker.tick_scheduled_scrapes")
    b = _broker_payload("app.workers.scraper_worker.run_scrape")
    c = _broker_payload("app.workers.scrape_scheduler_worker.tick_scheduled_scrapes")
    d = _broker_payload("app.workers.scrape_scheduler_worker.tick_scheduled_scrapes")
    r.lrange.return_value = [a, b, c, d]
    with patch("app.services.celery_queue_ops._redis_client", return_value=r):
        out = dedupe_scrape_tick_queue(keep=1)
    assert out["ok"] is True
    assert out["removed"] == 2
    assert out["after"] == 2  # one tick + run_scrape
    assert out["kept"] == 1
    pipe = r.pipeline.return_value
    pipe.delete.assert_called_once_with("scrape")
    args = pipe.rpush.call_args[0]
    assert args[0] == "scrape"
    assert len(args) == 3


def test_purge_thumbnail_warm_from_telegram_queue():
    r = MagicMock()
    r.ping.return_value = True
    warm = _broker_payload("app.workers.thumbnail_warm_worker.warm_media_thumbnails")
    imp = _broker_payload("app.workers.import_telegram_worker.process_import_job")
    r.lrange.return_value = [warm, imp, warm]
    with patch("app.services.celery_queue_ops._redis_client", return_value=r):
        out = purge_thumbnail_warm_from_telegram_queue()
    assert out["ok"] is True
    assert out["removed"] == 2
    assert out["after"] == 1
    pipe = r.pipeline.return_value
    pipe.delete.assert_called_once_with("telegram")
