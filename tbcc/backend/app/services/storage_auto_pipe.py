"""Auto-pipe Storage Hub lane media into quarantine review (Q&A batch cards)."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from app.data.aof_storage_hub_map import CONTENT_LANE_NETWORK_KEYS

logger = logging.getLogger(__name__)

REDIS_PREFIX = "tbcc:storage:auto_pipe"
DEBOUNCE_MIN_S = 15
DEBOUNCE_MAX_S = 600


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def storage_auto_pipe_enabled() -> bool:
    raw = (os.getenv("TBCC_STORAGE_AUTO_PIPE_ENABLED") or "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    try:
        override = (_redis().get(f"{REDIS_PREFIX}:global") or "").strip().lower()
        if override in ("0", "false", "no", "off"):
            return False
        if override in ("1", "true", "yes", "on"):
            return True
    except Exception:
        logger.debug("auto pipe global read failed", exc_info=True)
    return True


def set_storage_auto_pipe_enabled(enabled: bool) -> bool:
    val = "1" if enabled else "0"
    try:
        _redis().set(f"{REDIS_PREFIX}:global", val)
    except Exception:
        logger.debug("auto pipe global write failed", exc_info=True)
    return enabled


def auto_pipe_debounce_s() -> int:
    raw = (os.getenv("TBCC_STORAGE_AUTO_PIPE_DEBOUNCE_S") or "90").strip()
    try:
        val = int(raw)
    except ValueError:
        val = 90
    return max(DEBOUNCE_MIN_S, min(DEBOUNCE_MAX_S, val))


def lane_auto_pipe_enabled(lane_key: str) -> bool:
    if not storage_auto_pipe_enabled():
        return False
    key = (lane_key or "").strip().lower()
    if not key or key not in CONTENT_LANE_NETWORK_KEYS or key in ("inbox", "packs"):
        return False
    try:
        raw = (_redis().get(f"{REDIS_PREFIX}:lane:{key}") or "").strip().lower()
        if raw in ("0", "false", "no", "off"):
            return False
        if raw in ("1", "true", "yes", "on"):
            return True
    except Exception:
        logger.debug("auto pipe lane read failed lane=%s", key, exc_info=True)
    return True


def set_lane_auto_pipe_enabled(lane_key: str, enabled: bool) -> bool:
    key = (lane_key or "").strip().lower()
    if not key:
        return enabled
    try:
        _redis().set(f"{REDIS_PREFIX}:lane:{key}", "1" if enabled else "0")
    except Exception:
        logger.debug("auto pipe lane write failed lane=%s", key, exc_info=True)
    return enabled


def set_all_lanes_auto_pipe(enabled: bool) -> bool:
    """Global master toggle — sets global flag + every content lane."""
    set_storage_auto_pipe_enabled(enabled)
    for lane in CONTENT_LANE_NETWORK_KEYS:
        if lane in ("inbox", "packs"):
            continue
        set_lane_auto_pipe_enabled(lane, enabled)
    return enabled


def all_lanes_auto_pipe_on() -> bool:
    """True when every content lane has auto-pipe enabled (and global is on)."""
    if not storage_auto_pipe_enabled():
        return False
    for lane in CONTENT_LANE_NETWORK_KEYS:
        if lane in ("inbox", "packs"):
            continue
        if not lane_auto_pipe_enabled(lane):
            return False
    return True


def auto_pipe_batch_size(lane_key: str | None = None) -> int:
    from app.services.intake_scheduler import get_batch_size
    from app.services.quarantine_batch_review import review_batch_size

    return max(get_batch_size(lane_key), review_batch_size())


def _lane_key(lane_key: str) -> str:
    return (lane_key or "").strip().lower()


def _pending_task_key(lane_key: str) -> str:
    return f"{REDIS_PREFIX}:task:{_lane_key(lane_key)}"


def _last_signal_key(lane_key: str) -> str:
    return f"{REDIS_PREFIX}:last:{_lane_key(lane_key)}"


def _thread_key(lane_key: str) -> str:
    return f"{REDIS_PREFIX}:thread:{_lane_key(lane_key)}"


def signal_lane_auto_pipe(lane_key: str, message_thread_id: int) -> dict[str, Any]:
    """Debounce lane auto-pipe — coalesce rapid posts into one index job."""
    key = _lane_key(lane_key)
    if not key or not lane_auto_pipe_enabled(key):
        return {"ok": False, "skipped": True, "reason": "disabled", "lane_key": key}
    tid = int(message_thread_id)
    debounce = auto_pipe_debounce_s()
    try:
        r = _redis()
        r.set(_thread_key(key), str(tid), ex=debounce + 120)
        r.set(_last_signal_key(key), str(time.time()), ex=debounce + 120)
        if r.get(_pending_task_key(key)):
            return {"ok": True, "scheduled": False, "lane_key": key, "debounce_s": debounce}
        r.set(_pending_task_key(key), "1", ex=debounce + 120)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "lane_key": key}

    try:
        from app.workers.storage_auto_pipe_worker import run_lane_auto_pipe_task

        run_lane_auto_pipe_task.apply_async(args=[key], countdown=debounce)
        return {"ok": True, "scheduled": True, "lane_key": key, "debounce_s": debounce}
    except Exception as e:
        logger.warning("auto pipe schedule failed lane=%s: %s", key, e, exc_info=True)
        return {"ok": False, "error": str(e)[:200], "lane_key": key}


def run_lane_auto_pipe(lane_key: str) -> dict[str, Any]:
    """Index newest lane media as quarantine and queue Q&A batch review."""
    key = _lane_key(lane_key)
    if not key or not lane_auto_pipe_enabled(key):
        return {"ok": False, "skipped": True, "reason": "disabled", "lane_key": key}

    try:
        r = _redis()
        r.delete(_pending_task_key(key))
        last_raw = r.get(_last_signal_key(key))
        if last_raw:
            elapsed = time.time() - float(last_raw)
            if elapsed < auto_pipe_debounce_s() - 2:
                remaining = max(1, int(auto_pipe_debounce_s() - elapsed))
                from app.workers.storage_auto_pipe_worker import run_lane_auto_pipe_task

                r.set(_pending_task_key(key), "1", ex=remaining + 60)
                run_lane_auto_pipe_task.apply_async(args=[key], countdown=remaining)
                return {"ok": True, "rescheduled": True, "lane_key": key, "countdown_s": remaining}
        thread_raw = r.get(_thread_key(key))
        thread_id = int(thread_raw) if thread_raw else None
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "lane_key": key}

    if not thread_id:
        from app.data.aof_storage_hub_map import storage_map_by_key

        row = storage_map_by_key().get(key)
        if not row:
            return {"ok": False, "reason": "unmapped_lane", "lane_key": key}
        thread_id = int(row.message_thread_id)

    from app.database.session import SessionLocal
    from app.services.hub_intake_policy import hub_master_auto_approve_enabled
    from app.services.storage_topic_deposit import default_deposit_media_types, queue_storage_topic_deposit

    batch = auto_pipe_batch_size(key)
    qa_review_only = not hub_master_auto_approve_enabled()
    with SessionLocal() as db:
        report = queue_storage_topic_deposit(
            db,
            message_thread_id=int(thread_id),
            limit=batch,
            media_types=default_deposit_media_types(),
            include_topic_mirror=False,
            sent_cache=False,
            auto_pipe=True,
            qa_review_only=qa_review_only,
            commit=True,
        )
    return {"ok": bool(report.get("ok")), "lane_key": key, "report": report, "qa_review_only": qa_review_only}


def format_auto_pipe_status() -> str:
    from app.data.aof_storage_hub_map import GATEKEEPER_REVIEW_TOPIC_TITLE
    from app.services.gatekeeper_review import format_lane_pool_depth_html, review_thread_id
    from app.services.quarantine_batch_review import lane_quarantine_buffer_count, review_batch_size

    enabled = storage_auto_pipe_enabled()
    tid = review_thread_id()
    lines = [
        f"Auto-pipe: <b>{'ON' if enabled else 'OFF'}</b>",
        f"Q&A topic: <code>{tid or 'unset'}</code> · {GATEKEEPER_REVIEW_TOPIC_TITLE}",
        f"Review batch: <b>{review_batch_size()}</b> (+1 control)",
        f"Debounce: <b>{auto_pipe_debounce_s()}s</b>",
    ]
    try:
        from app.database.session import SessionLocal

        with SessionLocal() as db:
            lines.append(format_lane_pool_depth_html(db))
    except Exception:
        logger.debug("auto pipe pool depth line skipped", exc_info=True)
    if enabled:
        buffered = []
        for lane in sorted(CONTENT_LANE_NETWORK_KEYS):
            if lane in ("inbox", "packs"):
                continue
            n = lane_quarantine_buffer_count(lane)
            if n > 0:
                buffered.append(f"{lane}:{n}")
        if buffered:
            lines.append(f"Lane buffers: <code>{', '.join(buffered[:8])}</code>")
    return "\n".join(lines)
