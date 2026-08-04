"""Last SENT VAULT composer run per lane — shown on the lane control panel."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

REDIS_PREFIX = "tbcc:hub:lane:composer_status"


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _lane_key(network_key: str) -> str:
    return (network_key or "").strip().lower()


def record_lane_composer_status(network_key: str, report: dict[str, Any]) -> None:
    nk = _lane_key(network_key)
    if not nk:
        return
    built = int(report.get("albums_built") or 0)
    album_size = int(report.get("album_size") or 0)
    leftover = int(report.get("leftover_singles") or 0)
    erome_ok = sum(1 for a in report.get("albums") or [] if (a.get("erome") or {}).get("ok"))
    main_ok = sum(1 for a in report.get("albums") or [] if (a.get("main_group") or {}).get("ok"))
    payload = {
        "at": datetime.now(timezone.utc).isoformat(),
        "albums_built": built,
        "album_size": album_size,
        "leftover_singles": leftover,
        "main_group_ok": main_ok,
        "erome_ok": erome_ok,
        "album_urls": [
            (a.get("erome") or {}).get("album_url")
            for a in (report.get("albums") or [])[:3]
            if (a.get("erome") or {}).get("album_url")
        ],
    }
    try:
        _redis().set(f"{REDIS_PREFIX}:{nk}", json.dumps(payload))
    except Exception:
        logger.debug("lane composer status write failed nk=%s", nk, exc_info=True)


def lane_composer_status(network_key: str) -> dict[str, Any] | None:
    nk = _lane_key(network_key)
    if not nk:
        return None
    try:
        raw = _redis().get(f"{REDIS_PREFIX}:{nk}")
        if not raw:
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        logger.debug("lane composer status read failed nk=%s", nk, exc_info=True)
        return None


def format_lane_composer_status_line(network_key: str) -> str | None:
    data = lane_composer_status(network_key)
    if not data:
        return None
    built = int(data.get("albums_built") or 0)
    album_size = int(data.get("album_size") or 0)
    leftover = int(data.get("leftover_singles") or 0)
    parts = [f"<b>SENT VAULT composer:</b> {built} × {album_size}"]
    if leftover:
        parts.append(f"leftover {leftover}")
    main_ok = int(data.get("main_group_ok") or 0)
    erome_ok = int(data.get("erome_ok") or 0)
    if main_ok:
        parts.append(f"Loot preview {main_ok}")
    if erome_ok:
        parts.append(f"Erome {erome_ok}")
    return " · ".join(parts)
