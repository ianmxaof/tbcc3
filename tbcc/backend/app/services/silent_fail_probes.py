"""Silent-fail probes — readonly class-2 verdicts (ok | stale | never_seen | idle | blocked).

External-stop helpers for /silent-fail. No restarts, no Start bots, no writes.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

VERDICTS = frozenset({"ok", "stale", "never_seen", "idle", "blocked"})


def _env_flag(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return default


def _revenue_island_active() -> bool:
    return _env_flag("TBCC_REVENUE_ISLAND_ACTIVE", False)


def storage_hub_r2_export_enabled() -> bool:
    """Mirror celery_app Beat gate for storage-hub-r2-export."""
    raw = (os.getenv("TBCC_STORAGE_HUB_R2_EXPORT_ENABLED") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return _revenue_island_active()


def storage_hub_r2_export_interval_minutes() -> int:
    raw = (os.getenv("TBCC_STORAGE_HUB_R2_EXPORT_MINUTES") or "10").strip()
    try:
        return max(5, min(59, int(raw)))
    except ValueError:
        return 10


def verdict_from_last_success(
    *,
    enabled: bool,
    last_success_ts: float | None,
    interval_minutes: int,
    now: float | None = None,
    stale_mult: float = 2.0,
) -> str:
    """
    Class-2 / class-3 verdict from enablement + last success unix ts.

    last_success_ts None or <=0 → never_seen when enabled; idle when disabled.
    """
    if not enabled:
        return "idle"
    ts = float(last_success_ts or 0.0)
    if ts <= 0.0:
        return "never_seen"
    now_f = float(now if now is not None else time.time())
    interval_s = max(1.0, float(interval_minutes) * 60.0)
    age = max(0.0, now_f - ts)
    if age > interval_s * max(1.0, float(stale_mult)):
        return "stale"
    return "ok"


def probe_intake_lane(
    lane_key: str,
    *,
    now: float | None = None,
    stale_mult: float = 2.0,
) -> dict[str, Any]:
    """Readonly intake last_run probe (Redis via intake_scheduler)."""
    from app.services import intake_scheduler as intake

    lane = (lane_key or "").strip().lower()
    if not lane:
        return {
            "id": "intake_lane_last_run",
            "lane_key": "",
            "verdict": "blocked",
            "enabled": False,
            "error": "lane_key required",
            "stop_kind": "redis",
        }

    try:
        enabled = intake.intake_scheduler_enabled()
        interval = intake.get_interval_minutes(lane)
        last = float(intake.get_last_run_ts(lane) or 0.0)
    except Exception as e:
        logger.debug("intake probe failed lane=%s", lane, exc_info=True)
        return {
            "id": "intake_lane_last_run",
            "lane_key": lane,
            "verdict": "blocked",
            "enabled": None,
            "error": str(e)[:300],
            "stop_kind": "redis",
        }

    verdict = verdict_from_last_success(
        enabled=enabled,
        last_success_ts=last if last > 0 else None,
        interval_minutes=interval,
        now=now,
        stale_mult=stale_mult,
    )
    age_s = None
    if last > 0:
        age_s = max(0.0, float(now if now is not None else time.time()) - last)

    return {
        "id": "intake_lane_last_run",
        "lane_key": lane,
        "verdict": verdict,
        "enabled": enabled,
        "interval_min": interval,
        "last_run_ts": last,
        "age_s": age_s,
        "stale_mult": stale_mult,
        "stop_kind": "redis",
        "stop_evidence": f"tbcc:intake:lane:{lane}:last_run={last}",
    }


def probe_intake_all(
    *,
    now: float | None = None,
    stale_mult: float = 2.0,
) -> dict[str, Any]:
    """Probe every intake lane; aggregate worst class-2 verdict."""
    from app.services import intake_scheduler as intake

    try:
        enabled = intake.intake_scheduler_enabled()
        lanes = intake.scheduler_lane_keys()
    except Exception as e:
        return {
            "id": "intake_all_lanes",
            "verdict": "blocked",
            "enabled": None,
            "error": str(e)[:300],
            "lanes": [],
        }

    if not enabled:
        return {
            "id": "intake_all_lanes",
            "verdict": "idle",
            "enabled": False,
            "lanes": [],
            "stop_kind": "redis",
        }

    rows = [
        probe_intake_lane(lane, now=now, stale_mult=stale_mult) for lane in lanes
    ]
    order = {"never_seen": 0, "stale": 1, "blocked": 2, "ok": 3, "idle": 4}
    worst = min(rows, key=lambda r: order.get(str(r.get("verdict")), 9)) if rows else None
    return {
        "id": "intake_all_lanes",
        "verdict": (worst or {}).get("verdict", "ok"),
        "enabled": True,
        "lanes": rows,
        "worst_lane": (worst or {}).get("lane_key"),
        "stop_kind": "redis",
    }


def _parse_exported_at(raw: str | None) -> float | None:
    if not raw or not str(raw).strip():
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    r2 = parsed.get("r2")
    if not isinstance(r2, dict):
        return None
    stamp = str(r2.get("exported_at") or "").strip()
    if not stamp:
        return None
    try:
        dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def latest_r2_exported_at_ts(db, *, sample: int = 80) -> float | None:
    """Max exported_at among recent Media rows that carry classification_json.r2."""
    from app.models.media import Media

    lim = max(10, min(int(sample), 500))
    rows = (
        db.query(Media.id, Media.classification_json)
        .filter(Media.classification_json.isnot(None))
        .filter(Media.classification_json.contains('"exported_at"'))
        .order_by(Media.id.desc())
        .limit(lim)
        .all()
    )
    best: float | None = None
    for _mid, raw in rows:
        ts = _parse_exported_at(raw)
        if ts is None:
            continue
        if best is None or ts > best:
            best = ts
    return best


def count_hub_missing_r2_sample(db, *, limit: int = 20) -> int:
    """How many hub-export candidates still lack R2 (capped sample)."""
    try:
        from app.services.storage_hub_r2_export import iter_storage_hub_media_ids

        ids = iter_storage_hub_media_ids(
            db, since_id=0, limit=limit, only_missing_r2=True
        )
        return len(ids)
    except Exception:
        logger.debug("missing-r2 sample failed", exc_info=True)
        return -1


_R2_TICK_KEY = "tbcc:storage_hub_r2:last_tick"


def _redis_client():
    from urllib.parse import urlparse

    import redis

    u = (os.getenv("REDIS_URL") or "").strip()
    if not u:
        raise RuntimeError("REDIS_URL unset")
    p = urlparse(u)
    return redis.Redis(
        host=p.hostname,
        port=p.port or 6379,
        password=p.password,
        db=int((p.path or "/0").lstrip("/") or 0),
    )


def get_storage_hub_r2_last_tick_ts() -> float:
    """Unix ts of last Beat/batch attempt (incl. exported=0 / all-fail)."""
    try:
        raw = _redis_client().get(_R2_TICK_KEY)
        if raw is not None:
            return float(raw)
    except Exception:
        logger.debug("r2 last_tick read failed", exc_info=True)
    return 0.0


def mark_storage_hub_r2_tick() -> None:
    """Stamp that storage-hub-r2-export ran (success optional)."""
    try:
        _redis_client().set(_R2_TICK_KEY, str(time.time()))
    except Exception:
        logger.debug("r2 last_tick write failed", exc_info=True)


def probe_storage_hub_r2_export(
    db,
    *,
    now: float | None = None,
    stale_mult: float = 3.0,
    sample: int = 80,
) -> dict[str, Any]:
    """
    Class-2 probe for Beat key storage-hub-r2-export.

    Cadence uses Redis ``last_tick`` (Beat attempt) when present so "firing but
    all downloads fail" is not confused with "never fired". Successful
    ``exported_at`` stays in the payload for export-lag visibility.
    """
    enabled = storage_hub_r2_export_enabled()
    interval = storage_hub_r2_export_interval_minutes()
    if not enabled:
        return {
            "id": "storage_hub_r2_export",
            "beat_key": "storage-hub-r2-export",
            "verdict": "idle",
            "enabled": False,
            "interval_min": interval,
            "stop_kind": "db",
        }

    try:
        last_export = latest_r2_exported_at_ts(db, sample=sample)
        pending = count_hub_missing_r2_sample(db)
        last_tick = float(get_storage_hub_r2_last_tick_ts() or 0.0)
    except Exception as e:
        logger.debug("r2 export probe failed", exc_info=True)
        return {
            "id": "storage_hub_r2_export",
            "beat_key": "storage-hub-r2-export",
            "verdict": "blocked",
            "enabled": True,
            "error": str(e)[:300],
            "stop_kind": "db",
        }

    # Prefer Beat-attempt stamp; fall back to last successful export for older islands.
    cadence_ts = last_tick if last_tick > 0 else last_export
    verdict = verdict_from_last_success(
        enabled=True,
        last_success_ts=cadence_ts if cadence_ts else None,
        interval_minutes=interval,
        now=now,
        stale_mult=stale_mult,
    )
    now_f = float(now if now is not None else time.time())
    age_s = None
    if cadence_ts is not None and float(cadence_ts) > 0:
        age_s = max(0.0, now_f - float(cadence_ts))
    export_age_s = None
    if last_export is not None and float(last_export) > 0:
        export_age_s = max(0.0, now_f - float(last_export))
    export_lag = bool(
        pending and pending > 0
        and last_tick > 0
        and (last_export is None or (export_age_s or 0) > interval * 60 * stale_mult)
    )

    return {
        "id": "storage_hub_r2_export",
        "beat_key": "storage-hub-r2-export",
        "verdict": verdict,
        "enabled": True,
        "interval_min": interval,
        "last_exported_at_ts": last_export,
        "last_tick_ts": last_tick if last_tick > 0 else None,
        "age_s": age_s,
        "export_age_s": export_age_s,
        "pending_missing_sample": pending,
        "export_lag": export_lag,
        "stale_mult": stale_mult,
        "stop_kind": "redis" if last_tick > 0 else "db",
        "stop_evidence": (
            f"last_tick={last_tick or 0} "
            f"max(exported_at) ts={last_export} "
            f"pending_missing~{pending} export_lag={export_lag}"
        ),
    }


def probe_enrich_backlog(
    *,
    now: float | None = None,
    stale_mult: float = 2.0,
) -> dict[str, Any]:
    """
    Class-2 probe for Beat key enrich-backlog-sweep.

    Side-effect evidence: Redis ``tbcc:enrich_backlog:last_success`` stamped when
    the tick completes (including intentional skips). Disabled → idle.
    """
    from app.services import enrich_backlog as eb

    enabled = eb.backlog_enabled()
    interval = eb.backlog_interval_minutes()
    if not enabled:
        return {
            "id": "enrich_backlog",
            "beat_key": "enrich-backlog-sweep",
            "verdict": "idle",
            "enabled": False,
            "interval_min": interval,
            "stop_kind": "redis",
        }

    try:
        last = float(eb.get_last_success_ts() or 0.0)
    except Exception as e:
        logger.debug("enrich backlog probe failed", exc_info=True)
        return {
            "id": "enrich_backlog",
            "beat_key": "enrich-backlog-sweep",
            "verdict": "blocked",
            "enabled": True,
            "error": str(e)[:300],
            "stop_kind": "redis",
        }

    verdict = verdict_from_last_success(
        enabled=True,
        last_success_ts=last if last > 0 else None,
        interval_minutes=interval,
        now=now,
        stale_mult=stale_mult,
    )
    age_s = None
    if last > 0:
        age_s = max(0.0, float(now if now is not None else time.time()) - last)

    return {
        "id": "enrich_backlog",
        "beat_key": "enrich-backlog-sweep",
        "verdict": verdict,
        "enabled": True,
        "interval_min": interval,
        "last_success_ts": last,
        "age_s": age_s,
        "stale_mult": stale_mult,
        "stop_kind": "redis",
        "stop_evidence": f"tbcc:enrich_backlog:last_success={last}",
    }
