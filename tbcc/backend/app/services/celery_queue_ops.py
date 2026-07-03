"""Redis Celery queue depth and safe purge helpers."""

from __future__ import annotations

import json
import os
from collections import Counter
from typing import Any

DEFAULT_QUEUES = ("celery", "post", "post_scheduler", "scrape", "subscription", "telegram")


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


def _decode_celery_broker_message(raw: bytes | str) -> tuple[str, list | None]:
    """Return (task_name, args_list) from a Redis Celery/Kombu payload."""
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")
        outer = json.loads(raw)
        if isinstance(outer, dict):
            headers = outer.get("headers") or {}
            task = str(headers.get("task") or "unknown")
            body_raw = outer.get("body")
            if isinstance(body_raw, str) and body_raw:
                import base64

                inner = json.loads(base64.b64decode(body_raw))
                if isinstance(inner, list) and inner:
                    args = inner[0]
                    if isinstance(args, list):
                        return task, args
            return task, None
        if isinstance(outer, list) and len(outer) > 1 and isinstance(outer[1], dict):
            task = str(outer[1].get("task") or "unknown")
            envelope = outer[0]
            if isinstance(envelope, list) and envelope:
                args = envelope[0]
                if isinstance(args, list):
                    return task, args
    except Exception:
        pass
    return "unknown", None


def _task_name_from_broker_payload(raw: bytes | str) -> str:
    task, _ = _decode_celery_broker_message(raw)
    return task


def _extract_post_scheduled_text_id(raw: bytes | str) -> int | None:
    """First positional arg of post_scheduled_text Celery task, if present."""
    task, args = _decode_celery_broker_message(raw)
    if "post_scheduled_text" not in task or not args:
        return None
    try:
        return int(args[0])
    except (TypeError, ValueError, IndexError):
        return None


def audit_post_queue(queue_name: str = "post") -> dict[str, Any]:
    """Count pending post_scheduled_text tasks per scheduler id."""
    try:
        r = _redis_client()
        r.ping()
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}

    items = r.lrange(queue_name, 0, -1) or []
    by_post: Counter[int] = Counter()
    by_task: Counter[str] = Counter()
    for raw in items:
        task = _task_name_from_broker_payload(raw)
        by_task[task] += 1
        pid = _extract_post_scheduled_text_id(raw)
        if pid is not None:
            by_post[int(pid)] += 1
    dupes = {k: v for k, v in by_post.items() if v > 1}
    return {
        "ok": True,
        "queue": queue_name,
        "length": len(items),
        "tasks": dict(by_task.most_common(20)),
        "post_scheduled_text_by_id": dict(sorted(by_post.items())),
        "duplicate_post_ids": dupes,
        "duplicate_tasks_total": sum(v - 1 for v in dupes.values()),
    }


def dedupe_post_scheduled_text_queue(
    queue_name: str = "post",
    *,
    keep: str = "oldest",
) -> dict[str, Any]:
    """
    Remove duplicate post_scheduled_text tasks (same post_id), keep one per id.
    keep=oldest retains the task closest to the consumer end (FIFO tail).
    """
    if keep not in ("oldest", "newest"):
        return {"ok": False, "error": "keep must be oldest or newest"}
    try:
        r = _redis_client()
        r.ping()
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}

    items = r.lrange(queue_name, 0, -1) or []
    before = len(items)
    if before == 0:
        return {"ok": True, "queue": queue_name, "before": 0, "after": 0, "removed": 0}

    seen: set[int] = set()
    drop: set[int] = set()
    indices = range(len(items) - 1, -1, -1) if keep == "oldest" else range(len(items))
    for i in indices:
        pid = _extract_post_scheduled_text_id(items[i])
        if pid is None:
            continue
        if pid in seen:
            drop.add(i)
        else:
            seen.add(pid)

    kept = [items[i] for i in range(len(items)) if i not in drop]
    if len(kept) != before:
        pipe = r.pipeline()
        pipe.delete(queue_name)
        if kept:
            pipe.rpush(queue_name, *kept)
        pipe.execute()

    return {
        "ok": True,
        "queue": queue_name,
        "before": before,
        "after": len(kept),
        "removed": before - len(kept),
        "kept_post_ids": sorted(seen),
    }


def purge_queue_tasks_matching(
    queue_name: str,
    *,
    task_substrings: list[str],
) -> dict[str, Any]:
    """Remove pending broker tasks whose Celery task name contains any substring."""
    needles = [s.strip() for s in task_substrings if s and s.strip()]
    if not needles:
        return {"ok": False, "error": "no task_substrings specified"}
    try:
        r = _redis_client()
        r.ping()
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}

    items = r.lrange(queue_name, 0, -1) or []
    before = len(items)
    if before == 0:
        return {
            "ok": True,
            "queue": queue_name,
            "before": 0,
            "after": 0,
            "removed": 0,
            "removed_tasks": {},
        }

    kept: list[bytes | str] = []
    removed: Counter[str] = Counter()
    for raw in items:
        task = _task_name_from_broker_payload(raw)
        if any(n in task for n in needles):
            removed[task] += 1
        else:
            kept.append(raw)

    if len(kept) != before:
        pipe = r.pipeline()
        pipe.delete(queue_name)
        if kept:
            pipe.rpush(queue_name, *kept)
        pipe.execute()

    return {
        "ok": True,
        "queue": queue_name,
        "before": before,
        "after": len(kept),
        "removed": before - len(kept),
        "removed_tasks": dict(removed.most_common(20)),
    }


def purge_post_pool_tasks_from_queue(queue_name: str = "post") -> dict[str, Any]:
    """Drop pool auto-post jobs so scheduled-post drains are not stuck behind them."""
    return purge_queue_tasks_matching(
        queue_name,
        task_substrings=["app.workers.poster_worker.post_pool"],
    )


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
