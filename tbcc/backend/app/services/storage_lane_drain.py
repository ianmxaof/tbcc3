"""Drain-this-lane: loop the existing deposit primitive until a batch finds nothing
new and nothing duplicate, or a safety cap is hit.

No second import stack — reuses queue_storage_topic_deposit (storage_topic_deposit.py),
the same primitive every one-shot deposit already calls. The job is created there but run
here, in-process: this task already holds the single solo telegram worker, so dispatching
the job back onto that queue makes it wait behind the drain's own backlog.

Per-lane exclusivity via a Redis lock (same pattern as storage_auto_pipe.py's pending
task key); cancel a running drain by clearing that lock.
"""

from __future__ import annotations

import asyncio
import html
import json
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


def drain_heartbeat_stale_s() -> float:
    """How long a *running* drain may go without a heartbeat before it counts as dead.

    One batch is the unit here: an in-process import measured ~110s on 2026-09-04, and a
    large batch can run longer, so this is deliberately generous.
    """
    raw = (os.getenv("TBCC_LANE_DRAIN_HEARTBEAT_STALE_S") or "900").strip()
    try:
        return max(120.0, min(3600.0, float(raw)))
    except ValueError:
        return 900.0


def _lock_payload(token: str, state: str, *, iterations: int = 0, stored: int = 0) -> str:
    return json.dumps(
        {
            "token": token,
            "state": state,
            "ts": time.time(),
            "iterations": int(iterations),
            "stored": int(stored),
        }
    )


def read_lane_drain_lock(lane_key: str) -> dict[str, Any] | None:
    """Current lock contents, or None. Tolerates the pre-heartbeat bare-token format."""
    try:
        raw = _redis().get(_lock_key(lane_key))
    except Exception:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("token"):
            return data
    except (ValueError, TypeError):
        pass
    return {"token": str(raw), "state": "unknown", "ts": None}


def lane_drain_state(lane_key: str) -> dict[str, Any]:
    """Honest answer to 'what is this drain doing?'.

    A held lock does not mean work is happening. `queued` means the task is still waiting
    for the single solo telegram worker — normal on a busy queue, and the panel should say
    so rather than implying progress. `stale` means a running drain stopped heartbeating
    and its lock should be cleared.
    """
    lock = read_lane_drain_lock(lane_key)
    if not lock:
        return {"lane_key": _lane_key(lane_key), "held": False, "state": "idle"}
    ts = lock.get("ts")
    age = (time.time() - float(ts)) if ts else None
    state = str(lock.get("state") or "unknown")
    stale = bool(state == "running" and age is not None and age > drain_heartbeat_stale_s())
    return {
        "lane_key": _lane_key(lane_key),
        "held": True,
        "state": "stale" if stale else state,
        "age_s": int(age) if age is not None else None,
        "iterations": lock.get("iterations"),
        "stored": lock.get("stored"),
        "stale": stale,
    }


def is_lane_draining(lane_key: str) -> bool:
    """True while the lane is claimed — queued or running.

    Kept boolean for existing callers. Use lane_drain_state() when the difference between
    "waiting for a worker" and "actually importing" matters, which for anything the
    operator reads it does.
    """
    return bool(read_lane_drain_lock(lane_key))


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
        if not r.set(
            lock_key, _lock_payload(token, "queued"), nx=True, ex=int(drain_max_seconds()) + 300
        ):
            return {"ok": True, "already_running": True, "lane_key": key}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "lane_key": key}

    from app.services.storage_hub_op_status import post_hub_op_status

    status_message_id = post_hub_op_status(
        chat_id=int(chat_id),
        message_thread_id=tid,
        text=f"<i>{html.escape(key)} drain queued…</i>",
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


async def _run_import_job_inline(job_id: str) -> dict[str, Any] | None:
    """Run one already-created ImportJob on this worker instead of dispatching it.

    Returns the runner's own dict when it produced one, otherwise falls back to reading
    the ImportJob row. The row is the source of truth — never report "nothing stored"
    because an in-memory result was missing.
    """
    from app.services.channel_import_runner import run_channel_import_job_sync

    out: dict[str, Any] | None = None
    try:
        out = await asyncio.to_thread(run_channel_import_job_sync, job_id)
    except Exception as e:
        logger.warning("inline import job %s raised: %s", job_id, e, exc_info=True)

    if isinstance(out, dict) and out.get("status"):
        return out
    return _read_import_job(job_id)


def _read_import_job(job_id: str) -> dict[str, Any] | None:
    from app.database.session import SessionLocal
    from app.models.import_job import ImportJob
    from app.services.import_pipeline import job_to_public_dict

    try:
        with SessionLocal() as db:
            job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
            return job_to_public_dict(job) if job else None
    except Exception:
        logger.debug("could not read import job %s", job_id, exc_info=True)
        return None


def _import_counts(job_body: dict[str, Any]) -> dict[str, Any]:
    """Counters live at the top level from the runner, nested under `result` from the row."""
    nested = job_body.get("result")
    if isinstance(nested, dict) and ("stored" in nested or "skipped_duplicate" in nested):
        return nested
    return job_body


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
    from app.services.storage_topic_deposit import queue_storage_topic_deposit

    key = _lane_key(lane_key)
    lock_key = _lock_key(key)
    deadline = time.monotonic() + drain_max_seconds()
    max_iter = drain_max_iterations()

    total_stored = 0
    total_skipped = 0
    total_scanned = 0
    iterations = 0
    stop_reason = "unknown"
    # Scan cursor. Without it every batch restarts at the topic head, so once the head is
    # fully indexed the loop re-reads the same messages until the iteration cap and can
    # never satisfy its own stop condition. Measured 2026-09-04: 40 batches x 184 messages
    # = 7360 duplicates, 0 stored, and a `safety_cap_iterations` verdict on a lane that was
    # simply already indexed.
    cursor: int | None = None

    def _still_holds_lock() -> bool:
        try:
            lock = read_lane_drain_lock(key)
        except Exception:
            return True  # transient redis error must not look like an operator cancel
        if lock is None:
            return False  # operator cancelled, or the TTL expired
        return str(lock.get("token") or "") == token

    def _heartbeat(state: str = "running") -> None:
        """Re-stamp the lock so a dead worker is distinguishable from a slow one.

        Only refreshes a lock we still own — never resurrect one an operator cancelled.
        """
        try:
            lock = read_lane_drain_lock(key)
            if not lock or str(lock.get("token") or "") != token:
                return
            r = _redis()
            ttl = r.ttl(lock_key)
            payload = _lock_payload(token, state, iterations=iterations, stored=total_stored)
            if isinstance(ttl, int) and ttl > 0:
                r.set(lock_key, payload, ex=ttl)
            else:
                r.set(lock_key, payload, ex=int(drain_max_seconds()) + 300)
        except Exception:
            logger.debug("drain heartbeat failed lane=%s", key, exc_info=True)

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
        _heartbeat("running")
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
                # Run it here rather than dispatching to the queue we are sitting on.
                # This task holds the single solo telegram worker; a job dispatched from
                # here waits behind the whole backlog. Measured 2026-09-04: queued 24.5
                # minutes, ran 110 seconds, while the drain's patience was 90 seconds — so
                # every drain reported "worker may be offline" and quit after one batch
                # even though the import went on to store 105 items.
                enqueue=False,
                offset_id=cursor,
            )

        if not report.get("ok"):
            stop_reason = f"error:{report.get('error') or 'unknown'}"
            break

        job_id = str(report.get("job_id") or report.get("id") or "")
        if not job_id:
            stop_reason = "error:no_job_id"
            break

        job_body = await _run_import_job_inline(job_id)
        if not job_body:
            stop_reason = "import_no_result"
            break
        if str(job_body.get("status") or "").strip().lower() == "failed":
            stop_reason = f"import_failed:{job_body.get('error') or 'unknown'}"
            break

        result = _import_counts(job_body)
        stored = int(result.get("stored") or 0)
        skipped = int(result.get("skipped_duplicate") or 0)
        scanned = int(result.get("messages_scanned") or 0)
        oldest = result.get("oldest_scanned_message_id")
        total_stored += stored
        total_skipped += skipped
        total_scanned += scanned

        if oldest:
            # Next batch starts strictly below what this one already read.
            cursor = int(oldest)
        elif scanned == 0:
            # Nothing left below the cursor: the topic is exhausted, not merely deduped.
            stop_reason = "drained"
            break

        # With a cursor advancing each batch, an empty scan is the honest end of the topic.
        # stored==0 with duplicates only means "this stretch is already indexed" — older
        # uniques may still sit further back, so keep walking.
        if scanned == 0:
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
        "total_scanned": total_scanned,
        "last_cursor_message_id": cursor,
        "stop_reason": stop_reason,
    }
    await asyncio.to_thread(_report, _format_drain_done(summary))
    logger.info("lane drain done lane=%s %s", key, summary)
    return summary
