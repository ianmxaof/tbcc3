"""Celery queue purge helpers."""

from unittest.mock import MagicMock, patch

from app.services.celery_queue_ops import purge_post_pool_tasks_from_queue


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
