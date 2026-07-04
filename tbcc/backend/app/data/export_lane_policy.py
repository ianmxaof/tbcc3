"""Per-lane export policy defaults for the analytics-driven export flywheel."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app.data.aof_storage_hub_map import CONTENT_LANE_NETWORK_KEYS


@dataclass(frozen=True)
class LaneExportPolicy:
    network_key: str
    telegram_per_day: int = 4
    buffer_per_day: int = 2
    erome_per_day: int = 1
    min_pool_depth_before_export: int = 3
    preferred_hours_local: tuple[int, ...] = (11, 12, 19, 20)


def _env_int(key: str, default: int, *, lo: int, hi: int) -> int:
    raw = (os.getenv(key) or "").strip()
    if not raw:
        return default
    try:
        return max(lo, min(hi, int(raw)))
    except ValueError:
        return default


def default_telegram_per_day() -> int:
    return _env_int("TBCC_EXPORT_FLYWHEEL_DAILY_CAP_PER_LANE", 6, lo=1, hi=48)


def default_min_pool_depth() -> int:
    return _env_int("TBCC_LIVENESS_POOL_BACKUP_MIN_MEDIA", 3, lo=1, hi=50)


def lane_policy(network_key: str) -> LaneExportPolicy:
    key = (network_key or "").strip().lower()
    prefix = f"TBCC_EXPORT_LANE_{key.upper()}_" if key else ""
    hours_raw = (os.getenv(f"{prefix}PREFERRED_HOURS") or os.getenv("TBCC_EXPORT_FLYWHEEL_PREFERRED_HOURS") or "11,12,19,20").strip()
    hours: list[int] = []
    for part in hours_raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            hours.append(int(part) % 24)
        except ValueError:
            continue
    return LaneExportPolicy(
        network_key=key,
        telegram_per_day=_env_int(
            f"{prefix}TELEGRAM_PER_DAY",
            default_telegram_per_day(),
            lo=0,
            hi=48,
        ),
        buffer_per_day=_env_int(f"{prefix}BUFFER_PER_DAY", 2, lo=0, hi=24),
        erome_per_day=_env_int(f"{prefix}EROME_PER_DAY", 1, lo=0, hi=24),
        min_pool_depth_before_export=_env_int(
            f"{prefix}MIN_POOL_DEPTH",
            default_min_pool_depth(),
            lo=0,
            hi=100,
        ),
        preferred_hours_local=tuple(hours or (11, 12, 19, 20)),
    )


def all_lane_policies() -> dict[str, LaneExportPolicy]:
    return {key: lane_policy(key) for key in CONTENT_LANE_NETWORK_KEYS}


def policy_summary() -> list[dict[str, Any]]:
    return [
        {
            "network_key": p.network_key,
            "telegram_per_day": p.telegram_per_day,
            "buffer_per_day": p.buffer_per_day,
            "erome_per_day": p.erome_per_day,
            "min_pool_depth_before_export": p.min_pool_depth_before_export,
            "preferred_hours_local": list(p.preferred_hours_local),
        }
        for p in all_lane_policies().values()
    ]
