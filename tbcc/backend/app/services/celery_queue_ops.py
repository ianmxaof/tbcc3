"""Redis Celery queue depth and safe purge helpers."""

from __future__ import annotations

import json
import os
from collections import Counter
from typing import Any

DEFAULT_QUEUES = ("celery", "post", "scrape", "subscription", "telegram")


def _redis_client():
    import redis

    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.from_url(url, socket_connect_timeout=2)


def celery_queue_snapshot(sample_size: int = 120) -> dict[str, Any]:
    """Lengths + task-name histogram from the head of each queue."""
    try:
        r = _redis_client()
        r.ping()
    except Exception as e:
        return {"ok": False, "error": str(e)[:300], "queues": {}}

    out: dict[str, Any] = {"ok": True, "queues": {}}
    for qname in DEFAULT_QUEUES:
        length = int(r.llen(qname) or 0)
        hist: Counter[str] = Counter()
        if length > 0 and sample_size > 0:
            for raw in r.lrange(qname, 0, sample_size - 1):
                task = _task_name_from_broker_payload(raw)
                hist[task] += 1
        out["queues"][qname] = {
            "length": length,
            "sample_tasks": dict(hist.most_common(12)),
        }
    return out


def _task_name_from_broker_payload(raw: bytes | str) -> str:
    try:
        body = json.loads(raw)
        if isinstance(body, list) and len(body) > 1 and isinstance(body[1], dict):
            return str(body[1].get("task") or "unknown")
        if isinstance(body, dict):
            return str(body.get("headers", {}).get("task") or "unknown")
    except Exception:
        pass
    return "unknown"


def purge_celery_queues(
    queues: list[str] | None = None,
    *,
    min_length: int = 0,
) -> dict[str, Any]:
    """
    Delete pending tasks in Redis lists (Celery broker).
    min_length: only purge queues with at least this many pending tasks (0 = always purge listed).
    """
    names = [q.strip() for q in (queues or list(DEFAULT_QUEUES)) if q and q.strip()]
    if not names:
        return {"ok": False, "error": "no queues specified"}
    try:
        r = _redis_client()
        r.ping()
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}

    purged: dict[str, int] = {}
    skipped: dict[str, int] = {}
    for qname in names:
        n = int(r.llen(qname) or 0)
        if n < min_length:
            skipped[qname] = n
            continue
        if n > 0:
            r.delete(qname)
        purged[qname] = n
    return {"ok": True, "purged": purged, "skipped": skipped}
