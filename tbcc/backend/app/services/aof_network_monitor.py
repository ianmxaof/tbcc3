"""Aggregate AOF NETWORK pipeline status for dashboard polling."""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.data.aof_storage_hub_map import category_emoji_for_network_key
from app.data.operator_aof_paths import (
    OPERATOR_UTILITY_DIRS,
    operator_utility_path,
    watch_inbox_path,
    watch_library_path,
)
from app.services.local_lane_hub_map import lane_watch_targets

_COUNT_CACHE_TTL_S = 10.0
_count_cache: dict[str, tuple[float, int | None]] = {}
_count_lock = threading.Lock()
_refresh_lock = threading.Lock()
_refresh_running = False
_log_mtime_cache: dict[str, float] = {}

_MEDIA_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".mp4", ".mov", ".webm", ".avi", ".mkv"})


def _is_media_file(path: Path) -> bool:
    return path.suffix.lower() in _MEDIA_SUFFIXES


def _count_media_in_dir(path: Path, *, recursive: bool = True) -> int | None:
    if not path.is_dir():
        return None
    n = 0
    try:
        iterator = path.rglob("*") if recursive else path.iterdir()
        for entry in iterator:
            if entry.is_file() and _is_media_file(entry):
                n += 1
    except OSError:
        return None
    return n


def _peek_cached_count(key: str) -> int | None:
    with _count_lock:
        hit = _count_cache.get(key)
        if hit and (time.time() - hit[0]) < _COUNT_CACHE_TTL_S:
            return hit[1]
    return None


def _store_cached_count(key: str, val: int | None) -> None:
    with _count_lock:
        _count_cache[key] = (time.time(), val)


def _cached_media_count(
    key: str,
    path: Path,
    *,
    recursive: bool = True,
    scan_if_missing: bool = True,
) -> int | None:
    cached = _peek_cached_count(key)
    if cached is not None:
        return cached
    if not scan_if_missing:
        return None
    val = _count_media_in_dir(path, recursive=recursive)
    _store_cached_count(key, val)
    return val


def _refresh_all_media_counts() -> None:
    """Background folder scan — no process probes (keeps request threads free)."""
    inbox = watch_inbox_path()
    _cached_media_count(f"inbox:{inbox}", inbox, scan_if_missing=True)
    for target in lane_watch_targets():
        _cached_media_count(
            f"lane:{target.network_key}:{target.folder_path}",
            target.folder_path,
            scan_if_missing=True,
        )
    for key in ("unsorted", "stash_data", "gd_inbox"):
        try:
            util_path = operator_utility_path(key)
            _cached_media_count(f"util:{key}:{util_path}", util_path, scan_if_missing=True)
        except KeyError:
            continue


def _schedule_full_count_refresh() -> None:
    global _refresh_running
    with _refresh_lock:
        if _refresh_running:
            return
        _refresh_running = True

    def _run() -> None:
        global _refresh_running
        try:
            _refresh_all_media_counts()
        finally:
            with _refresh_lock:
                _refresh_running = False

    threading.Thread(target=_run, name="aof-network-count-refresh", daemon=True).start()


def _tail_jsonl(path: Path | None, max_records: int = 25) -> list[dict[str, Any]]:
    if not path or not path.is_file() or max_records <= 0:
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            chunk = min(size, 384_000)
            f.seek(max(0, size - chunk))
            raw = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for ln in [x.strip() for x in raw.splitlines() if x.strip()][-max_records:]:
        try:
            row = json.loads(ln)
            if isinstance(row, dict):
                out.append(row)
        except json.JSONDecodeError:
            out.append({"parse_error": True, "preview": ln[:300]})
    return out


def _activity_since(rows: list[dict[str, Any]], *, seconds: float, actions: frozenset[str]) -> int:
    cutoff = datetime.now(timezone.utc).timestamp() - seconds
    n = 0
    for row in rows:
        action = str(row.get("action") or "").strip().lower()
        if action not in actions:
            continue
        ts_raw = row.get("ts")
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError):
            continue
        if ts >= cutoff:
            n += 1
    return n


def _log_mtime(path: Path | None) -> float:
    if not path or not path.is_file():
        return 0.0
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _maybe_invalidate_counts_from_logs(watch_log: Path | None, hub_log: Path | None) -> None:
    """Drop folder count cache when JSONL logs change (fresh moves/uploads)."""
    changed = False
    for key, path in (("watch", watch_log), ("hub", hub_log)):
        if not path:
            continue
        mt = _log_mtime(path)
        prev = _log_mtime_cache.get(key, 0.0)
        if mt > prev:
            _log_mtime_cache[key] = mt
            changed = True
    if changed:
        with _count_lock:
            _count_cache.clear()


def _hub_album_buffer_stats(lanes: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"enabled": False, "total_pending": 0, "by_topic": {}}
    try:
        from app.services.storage_hub_album_intake import dest_key_for_topic, pending_count, storage_hub_album_intake_enabled

        if not storage_hub_album_intake_enabled():
            return out
        out["enabled"] = True
        total = 0
        by_topic: dict[str, int] = {}
        for lane in lanes:
            tid = lane.get("message_thread_id")
            if not tid:
                continue
            key = dest_key_for_topic(int(tid))
            n = pending_count(key)
            if n > 0:
                by_topic[str(tid)] = n
                total += n
        out["total_pending"] = total
        out["by_topic"] = by_topic
    except Exception:
        pass
    return out


def _pipeline_active(
    *,
    moves_1m: int,
    uploads_1m: int,
    counters: dict[str, Any],
) -> bool:
    if moves_1m > 0 or uploads_1m > 0:
        return True
    now = time.time()
    for field in ("last_move_ts", "last_upload_ts"):
        ts = counters.get(field)
        if isinstance(ts, (int, float)) and (now - float(ts)) < 120:
            return True
    return False


def _log_path_from_env(name: str, default: Path | None = None) -> Path | None:
    raw = (os.environ.get(name) or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return default.resolve() if default else None


def collect_aof_network_status(*, invalidate_counts: bool = False, fast: bool = True) -> dict[str, Any]:
    """Pipeline snapshot for dashboard polling. ``fast=True`` returns cached counts only (<1s)."""
    if invalidate_counts:
        with _count_lock:
            _count_cache.clear()

    from app.services import local_lane_hub_control as lhc
    from app.services import watch_folder_control as wfc
    from app.services.local_lane_hub_deposit import local_lane_hub_enabled, local_lane_hub_log_path
    from app.services.local_lane_hub_ledger import ledger_stats

    scan = not fast
    watch_pids = wfc._find_daemon_pids(fast=fast)
    hub_pids = lhc._find_daemon_pids(fast=fast)

    inbox = watch_inbox_path()
    library = watch_library_path()
    watch_log = _log_path_from_env("TBCC_WATCH_LOG")
    hub_log = local_lane_hub_log_path()
    _maybe_invalidate_counts_from_logs(watch_log, hub_log)

    from app.services.aof_pipeline_counters import read_counters

    counters = read_counters()
    ledger = ledger_stats()
    by_lane = ledger.get("by_lane") or {}

    inbox_media = _cached_media_count(
        f"inbox:{inbox}",
        inbox,
        recursive=True,
        scan_if_missing=scan,
    )
    watch_recent = _tail_jsonl(watch_log, 30)
    hub_recent = _tail_jsonl(hub_log, 30)

    lanes_out: list[dict[str, Any]] = []
    total_lane_media = 0
    hub_pending_uploads = 0
    for target in lane_watch_targets():
        count = _cached_media_count(
            f"lane:{target.network_key}:{target.folder_path}",
            target.folder_path,
            scan_if_missing=scan,
        )
        if count is not None:
            total_lane_media += count
        lane_ledger_uploads = int(by_lane.get(target.network_key) or 0)
        # Files stay on disk after upload (ledger dedupes, it doesn't move/delete) —
        # disk count alone can never signal "drained". Pending = on-disk minus what
        # this lane's ledger already accounts for (clamped so backfilled/moved files
        # can't push it negative). None when the disk count itself is still scanning.
        lane_pending = max(0, count - lane_ledger_uploads) if count is not None else None
        if lane_pending is not None:
            hub_pending_uploads += lane_pending
        lanes_out.append(
            {
                "network_key": target.network_key,
                "folder_name": target.folder_name,
                "path": str(target.folder_path),
                "exists": target.folder_path.is_dir(),
                "media_count": count,
                "ledger_uploads": lane_ledger_uploads,
                "pending_uploads": lane_pending,
                "message_thread_id": target.message_thread_id,
                "topic_title": target.topic_title,
                "emoji": category_emoji_for_network_key(target.network_key),
            }
        )

    unsorted_path = operator_utility_path("unsorted")
    unsorted_count = _cached_media_count(
        f"util:unsorted:{unsorted_path}",
        unsorted_path,
        scan_if_missing=scan or _peek_cached_count(f"util:unsorted:{unsorted_path}") is None,
    )
    utilities: dict[str, Any] = {
        "unsorted": {
            "label": OPERATOR_UTILITY_DIRS.get("unsorted", "Unsorted"),
            "path": str(unsorted_path),
            "exists": unsorted_path.is_dir(),
            "media_count": unsorted_count,
        }
    }
    if scan:
        for key in ("stash_data", "gd_inbox"):
            try:
                util_path = operator_utility_path(key)
                utilities[key] = {
                    "label": OPERATOR_UTILITY_DIRS.get(key, key),
                    "path": str(util_path),
                    "exists": util_path.is_dir(),
                    "media_count": _cached_media_count(f"util:{key}:{util_path}", util_path),
                }
            except KeyError:
                continue

    moves_5m = _activity_since(watch_recent, seconds=300, actions=frozenset({"move"}))
    uploads_5m = _activity_since(hub_recent, seconds=300, actions=frozenset({"upload"}))
    moves_1m = _activity_since(watch_recent, seconds=60, actions=frozenset({"move", "dry_run"}))
    uploads_1m = _activity_since(hub_recent, seconds=60, actions=frozenset({"upload", "dry_run"}))
    errors_1m = _activity_since(hub_recent, seconds=60, actions=frozenset({"error"}))
    skips_1m = _activity_since(
        hub_recent,
        seconds=60,
        actions=frozenset({"skip"}),
    )
    hub_buffer = _hub_album_buffer_stats(lanes_out)
    pipeline_active = _pipeline_active(moves_1m=moves_1m, uploads_1m=uploads_1m, counters=counters)

    counts_stale = fast and any(
        row.get("media_count") is None for row in lanes_out
    ) or (fast and inbox_media is None)
    if counts_stale and not invalidate_counts:
        _schedule_full_count_refresh()

    total_ledger = int(ledger.get("total_uploads") or 0)

    return {
        "ok": True,
        "ts": datetime.now(timezone.utc).isoformat(),
        "root": str(library),
        "counts_mode": "fast" if fast else "full",
        "counts_refreshing": counts_stale,
        "watch": {
            "running": bool(watch_pids),
            "pids": watch_pids,
            "inbox_path": str(inbox),
            "inbox_exists": inbox.is_dir(),
            "inbox_media_count": inbox_media,
            "library_path": str(library),
            "debounce_s": float(os.environ.get("TBCC_WATCH_DEBOUNCE_S") or "1.5"),
            "stable_wait_s": float(os.environ.get("TBCC_WATCH_STABLE_WAIT_S") or "2.0"),
            "aof_lane_folders": (os.environ.get("TBCC_WATCH_AOF_LANE_FOLDERS") or "1").strip().lower()
            not in ("0", "false", "no", "off"),
            "log_path": str(watch_log) if watch_log else None,
        },
        "lane_hub": {
            "enabled": local_lane_hub_enabled(),
            "running": bool(hub_pids),
            "pids": hub_pids,
            "ledger": ledger,
            "album_buffer": hub_buffer,
            "log_path": str(hub_log) if hub_log else None,
            "lanes": lanes_out,
        },
        "utilities": utilities,
        "counters": counters,
        "activity": {
            "watch_recent": watch_recent[-12:],
            "hub_recent": hub_recent[-12:],
            "moves_last_minute": moves_1m,
            "uploads_last_minute": uploads_1m,
            "moves_last_5m": moves_5m,
            "uploads_last_5m": uploads_5m,
            "errors_last_minute": errors_1m,
            "skips_last_minute": skips_1m,
            "pipeline_active": pipeline_active,
        },
        "summary": {
            "inbox_pending": inbox_media,
            "total_lane_media": total_lane_media,
            "unsorted_media": unsorted_count,
            "hub_uploads_total": total_ledger,
            "hub_pending_uploads": hub_pending_uploads,
            "hub_buffer_pending": hub_buffer.get("total_pending", 0),
            "lanes_watched": len(lanes_out),
            "watch_running": bool(watch_pids),
            "lane_hub_running": bool(hub_pids),
            "firehose_ready": bool(watch_pids) and bool(hub_pids),
        },
    }
