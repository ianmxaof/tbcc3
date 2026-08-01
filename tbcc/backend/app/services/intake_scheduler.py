"""Redis-backed intake batch cadence — batch size, interval, album size (operator-tunable)."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

REDIS_PREFIX = "tbcc:intake"
BATCH_MIN = 1
BATCH_MAX = 200
INTERVAL_MIN = 5
INTERVAL_MAX = 24 * 60
ALBUM_MIN = 1
ALBUM_MAX = 10


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def intake_scheduler_enabled() -> bool:
    raw = (os.getenv("TBCC_INTAKE_SCHEDULER_ENABLED") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return (os.getenv("TBCC_STORAGE_POOL_SEED_ENABLED") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _env_batch_default() -> int:
    raw = (os.getenv("TBCC_INTAKE_BATCH_SIZE") or os.getenv("TBCC_STORAGE_POOL_SEED_BATCH") or "8").strip()
    try:
        return min(max(int(raw), BATCH_MIN), BATCH_MAX)
    except ValueError:
        return 8


def _env_interval_default() -> int:
    raw_min = (os.getenv("TBCC_INTAKE_INTERVAL_MIN") or "").strip()
    if raw_min:
        try:
            return min(max(int(raw_min), INTERVAL_MIN), INTERVAL_MAX)
        except ValueError:
            pass
    raw_h = (os.getenv("TBCC_INTAKE_INTERVAL_HOURS") or os.getenv("TBCC_STORAGE_POOL_SEED_HOURS") or "4").strip()
    try:
        hours = max(1, min(24, int(raw_h)))
    except ValueError:
        hours = 4
    return min(max(hours * 60, INTERVAL_MIN), INTERVAL_MAX)


def _env_album_default() -> int:
    raw = (os.getenv("TBCC_INTAKE_ALBUM_SIZE") or "5").strip()
    try:
        return min(max(int(raw), ALBUM_MIN), ALBUM_MAX)
    except ValueError:
        return 5


def _key(suffix: str, lane_key: str | None = None) -> str:
    lane = (lane_key or "").strip().lower()
    if lane:
        return f"{REDIS_PREFIX}:lane:{lane}:{suffix}"
    return f"{REDIS_PREFIX}:global:{suffix}"


def get_batch_size(lane_key: str | None = None) -> int:
    lane = (lane_key or "").strip().lower()
    try:
        r = _redis()
        if lane:
            raw = r.get(_key("batch", lane))
            if raw is not None:
                return min(max(int(raw), BATCH_MIN), BATCH_MAX)
        raw = r.get(_key("batch"))
        if raw is not None:
            return min(max(int(raw), BATCH_MIN), BATCH_MAX)
    except Exception:
        logger.debug("intake batch read failed lane=%s", lane_key, exc_info=True)
    return _env_batch_default()


def get_interval_minutes(lane_key: str | None = None) -> int:
    lane = (lane_key or "").strip().lower()
    try:
        r = _redis()
        if lane:
            raw = r.get(_key("interval_min", lane))
            if raw is not None:
                return min(max(int(raw), INTERVAL_MIN), INTERVAL_MAX)
        raw = r.get(_key("interval_min"))
        if raw is not None:
            return min(max(int(raw), INTERVAL_MIN), INTERVAL_MAX)
    except Exception:
        logger.debug("intake interval read failed lane=%s", lane_key, exc_info=True)
    return _env_interval_default()


def get_album_size() -> int:
    try:
        raw = _redis().get(_key("album_size"))
        if raw is not None:
            return min(max(int(raw), ALBUM_MIN), ALBUM_MAX)
    except Exception:
        logger.debug("intake album_size read failed", exc_info=True)
    return _env_album_default()


def set_batch_size(value: int, lane_key: str | None = None) -> int:
    val = min(max(int(value), BATCH_MIN), BATCH_MAX)
    try:
        _redis().set(_key("batch", lane_key), str(val))
    except Exception:
        logger.debug("intake batch write failed", exc_info=True)
    return val


def set_interval_minutes(value: int, lane_key: str | None = None) -> int:
    val = min(max(int(value), INTERVAL_MIN), INTERVAL_MAX)
    try:
        _redis().set(_key("interval_min", lane_key), str(val))
    except Exception:
        logger.debug("intake interval write failed", exc_info=True)
    return val


def set_album_size(value: int) -> int:
    val = min(max(int(value), ALBUM_MIN), ALBUM_MAX)
    try:
        _redis().set(_key("album_size"), str(val))
    except Exception:
        logger.debug("intake album_size write failed", exc_info=True)
    return val


def adjust_batch_size(delta: int, lane_key: str | None = None) -> int:
    return set_batch_size(get_batch_size(lane_key) + int(delta), lane_key)


def adjust_interval_minutes(delta: int, lane_key: str | None = None) -> int:
    return set_interval_minutes(get_interval_minutes(lane_key) + int(delta), lane_key)


def adjust_album_size(delta: int) -> int:
    return set_album_size(get_album_size() + int(delta))


def get_last_run_ts(lane_key: str) -> float:
    key = (lane_key or "").strip().lower()
    if not key:
        return 0.0
    try:
        raw = _redis().get(_key("last_run", key))
        if raw is not None:
            return float(raw)
    except Exception:
        logger.debug("intake last_run read failed lane=%s", key, exc_info=True)
    return 0.0


def mark_lane_run(lane_key: str) -> None:
    key = (lane_key or "").strip().lower()
    if not key:
        return
    try:
        _redis().set(_key("last_run", key), str(time.time()))
    except Exception:
        logger.debug("intake last_run write failed lane=%s", key, exc_info=True)


def lane_due_for_run(lane_key: str, *, force: bool = False) -> bool:
    if force:
        return True
    key = (lane_key or "").strip().lower()
    if not key:
        return False
    elapsed = time.time() - get_last_run_ts(key)
    return elapsed >= get_interval_minutes(key) * 60


def scheduler_lane_keys() -> list[str]:
    """All content-lane keys + inbox for periodic deposit ticks."""
    from app.data.aof_storage_hub_map import CONTENT_LANE_NETWORK_KEYS

    keys = sorted(CONTENT_LANE_NETWORK_KEYS)
    if "inbox" not in keys:
        keys.append("inbox")
    return keys


def status_snapshot() -> dict[str, Any]:
    lanes = scheduler_lane_keys()
    per_lane = []
    for lane in lanes:
        last = get_last_run_ts(lane)
        per_lane.append(
            {
                "lane_key": lane,
                "batch_size": get_batch_size(lane),
                "interval_min": get_interval_minutes(lane),
                "last_run_ts": last,
                "due": lane_due_for_run(lane),
            }
        )
    return {
        "enabled": intake_scheduler_enabled(),
        "global_batch_size": get_batch_size(),
        "global_interval_min": get_interval_minutes(),
        "album_size": get_album_size(),
        "lanes": per_lane,
    }


def format_status_text() -> str:
    snap = status_snapshot()
    lines = [
        "<b>📥 Intake scheduler</b>",
        f"Enabled: <code>{'yes' if snap['enabled'] else 'no'}</code>",
        f"Global batch: <b>{snap['global_batch_size']}</b> · interval: <b>{snap['global_interval_min']}m</b>",
        f"Inbox album size: <b>{snap['album_size']}</b> (quarantine bundles)",
        "",
        "<i>Due lanes:</i>",
    ]
    due = [r for r in snap["lanes"] if r["due"]]
    if not due:
        lines.append("— none right now —")
    else:
        for row in due[:12]:
            lines.append(
                f"• <code>{row['lane_key']}</code> batch {row['batch_size']} · every {row['interval_min']}m"
            )
    return "\n".join(lines)
