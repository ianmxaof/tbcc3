"""Drain-this-lane: loop the existing deposit primitive until a batch finds nothing
new and nothing duplicate, or a safety cap is hit.

No second import stack — reuses queue_storage_topic_deposit + await_deposit_import_job
(storage_topic_deposit.py), the same primitive every one-shot deposit already calls.
Per-lane exclusivity via a Redis lock (same pattern as storage_auto_pipe.py's pending
task key); cancel a running drain by clearing that lock.
"""

from __future__ import annotations

import asyncio
import html
import logging
import os
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

REDIS_PREFIX = "tbcc:storage:drain"


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _lane_key(lane_key: str) -> str:
    return (lane_key or "").strip().lower()


def _lock_key(lane_key: str) -> str:
    return f"{REDIS_PREFIX}:lock:{_lane_key(lane_key)}"


def drain_max_iterations() -> int:
    raw = (os.getenv("TBCC_LANE_DRAIN_MAX_ITERATIONS") or "40").strip()
    try:
        return max(1, min(200, int(raw)))
    except ValueError:
        return 40


def drain_max_seconds() -> float:
    raw = (os.getenv("TBCC_LANE_DRAIN_MAX_SECONDS") or "1800").strip()
    try:
        return max(60.0, min(7200.0, float(raw)))
    except ValueError:
        return 1800.0


def is_lane_draining(lane_key: str) -> bool:
    try:
        return bool(_redis().get(_lock_key(lane_key)))
    except Exception:
        return False


def cancel_lane_drain(lane_key: str) -> bool:
    """Clear the drain lock — the running loop checks this before its next batch and stops."""
    try:
        r = _redis()
        key = _lock_key(lane_key)
        existed = bool(r.get(key))
        r.delete(key)
        return existed
    except Exception:
        return False


def start_lane_drain(
    lane_key: str,
    *,
    chat_id: int,
    message_thread_id: int | None = None,
) -> dict[str, Any]:
    """Acquire the per-lane drain lock and enqueue the drain task. Sync — call from a handler."""
    from app.data.aof_storage_hub_map import CONTENT_LANE_NETWORK_KEYS, storage_map_by_key

    key = _lane_key(lane_key)
    if not key or key not in CONTENT_LANE_NETWORK_KEYS or key in ("inbox", "packs"):
        return {"ok": False, "error": "invalid_lane", "lane_key": key}
    row = storage_map_by_key().get(key)
    tid = int(message_thread_id) if message_thread_id else (
        int(row.message_thread_id) if row and row.message_thread_id else None
    )
    if not tid:
        return {"ok": False, "error": "unmapped_lane", "lane_key": key}

    token = uuid.uuid4().hex
    try:
        r = _redis()
        lock_key = _lock_key(key)
        if not r.set(lock_key, token, nx=True, ex=int(drain_max_seconds()) + 300):
            return {"ok": True, "already_running": True, "lane_key": key}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "lane_key": key}

    from app.services.storage_hub_op_status import post_hub_op_status

    status_message_id = post_hub_op_status(
        chat_id=int(chat_id),
        message_thread_id=tid,
        text=f"<i>Draining {html.escape(key)}…</i>",
    )

    try:
        from app.workers.storage_lane_drain_worker import run_lane_drain_task

        run_lane_drain_task.delay(
            key,
            token=token,
            chat_id=int(chat_id),
            message_thread_id=tid,
            status_message_id=status_message_id,
        )
    except Exception as e:
        try:
            _redis().delete(_lock_key(key))
        except Exception:
            pass
        return {"ok": False, "error": str(e)[:200], "lane_key": key}

    return {
        "ok": True,
        "started": True,
        "lane_key": key,
        "status_message_id": status_message_id,
    }


def _format_drain_status(lane_key: str, iterations: int, total_stored: int) -> str:
    return (
        f"<i>Draining {html.escape(lane_key)}…</i> batch {iterations} · "
        f"{total_stored} stored so far"
    )


def _format_drain_done(summary: dict[str, Any]) -> str:
    lane = html.escape(str(summary.get("lane_key") or "?"))
    reason = summary.get("stop_reason")
    stored = summary.get("total_stored")
    skipped = summary.get("total_skipped_duplicate")
    iterations = summary.get("iterations")
    if reason == "drained":
        head = f"✅ <b>{lane} drained</b>"
    elif reason and str(reason).startswith("safety_cap"):
        head = f"⏸ <b>{lane} drain paused (safety cap)</b>"
    elif reason == "cancelled":
        head = f"⏹ <b>{lane} drain cancelled</b>"
    else:
        head = f"⚠️ <b>{lane} drain stopped</b>"
    return (
        f"{head}\n\n"
        f"<b>Stored:</b> {stored} · <b>Skipped (dup):</b> {skipped} · "
        f"<b>Batches:</b> {iterations}\n"
        f"<b>Reason:</b> <code>{html.escape(str(reason))}</code>"
    )


async def run_lane_drain(
    lane_key: str,
    *,
    token: str,
    chat_id: int,
    message_thread_id: int,
    status_message_id: int | None,
) -> dict[str, Any]:
    """Loop one deposit batch at a time until a batch is fully empty (stored==0 AND
    skipped_duplicate==0) or a safety cap fires. Re-reads auto-approve each batch so
    toggling it mid-drain takes effect on the next batch, not just at drain start."""
    from app.database.session import SessionLocal
    from app.services.hub_intake_policy import hub_master_auto_approve_enabled
    from app.services.storage_deposit_control import get_deposit_limit, get_deposit_media_types
    from app.services.storage_hub_op_status import edit_hub_op_status
    from app.services.storage_topic_deposit import (
        await_deposit_import_job,
        queue_storage_topic_deposit,
    )

    key = _lane_key(lane_key)
    lock_key = _lock_key(key)
    deadline = time.monotonic() + drain_max_seconds()
    max_iter = drain_max_iterations()

    total_stored = 0
    total_skipped = 0
    iterations = 0
    stop_reason = "unknown"

    def _still_holds_lock() -> bool:
        try:
            return _redis().get(lock_key) == token
        except Exception:
            return True  # transient redis error must not look like an operator cancel

    def _report(text: str) -> None:
        if not status_message_id:
            return
        try:
            edit_hub_op_status(chat_id=chat_id, message_id=status_message_id, text=text)
        except Exception:
            logger.debug("drain status edit failed lane=%s", key, exc_info=True)

    while True:
        if not _still_holds_lock():
            stop_reason = "cancelled"
            break
        if iterations >= max_iter:
            stop_reason = "safety_cap_iterations"
            break
        if time.monotonic() >= deadline:
            stop_reason = "safety_cap_seconds"
            break

        iterations += 1
        qa_review_only = not hub_master_auto_approve_enabled()
        limit = get_deposit_limit()
        media_types = get_deposit_media_types()

        await asyncio.to_thread(_report, _format_drain_status(key, iterations, total_stored))

        with SessionLocal() as db:
            report = queue_storage_topic_deposit(
                db,
                message_thread_id=int(message_thread_id),
                limit=limit,
                media_types=media_types,
                include_topic_mirror=False,
                sent_cache=False,
                auto_pipe=False,
                qa_review_only=qa_review_only,
                commit=True,
            )

        if not report.get("ok"):
            stop_reason = f"error:{report.get('error') or 'unknown'}"
            break

        job_id = str(report.get("job_id") or report.get("id") or "")
        job_body = await await_deposit_import_job(
            job_id,
            limit=limit,
            media_types=media_types,
            index_only=bool(report.get("index_only")),
            sent_cache=False,
        )
        if not job_body:
            stop_reason = "import_timeout"
            break
        if str(job_body.get("status") or "").strip().lower() == "failed":
            stop_reason = f"import_failed:{job_body.get('error') or 'unknown'}"
            break

        result = job_body.get("result") if isinstance(job_body.get("result"), dict) else {}
        stored = int(result.get("stored") or 0)
        skipped = int(result.get("skipped_duplicate") or 0)
        total_stored += stored
        total_skipped += skipped

        # Cursor lock: newest-first can sit on already-indexed heads while older uniques
        # remain further back — only stop when a batch is fully empty, not just stored==0.
        if stored == 0 and skipped == 0:
            stop_reason = "drained"
            break

    try:
        _redis().delete(lock_key)
    except Exception:
        pass

    summary = {
        "ok": True,
        "lane_key": key,
        "iterations": iterations,
        "total_stored": total_stored,
        "total_skipped_duplicate": total_skipped,
        "stop_reason": stop_reason,
    }
    await asyncio.to_thread(_report, _format_drain_done(summary))
    logger.info("lane drain done lane=%s %s", key, summary)
    return summary
