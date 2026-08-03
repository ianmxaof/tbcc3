"""Resolve Loot Room forum subtopic ids for a network lane (live Telegram → Redis → static map)."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from app.data.aof_main_group_topic_map import (
    AOF_MAIN_GROUP_TOPIC_MAP,
    main_topic_for_network_key,
)
from app.data.aof_network import MAIN_GROUP_IDENT, match_topic_to_network_key, network_channel_by_key

logger = logging.getLogger(__name__)

REDIS_PREFIX = "tbcc:loot_room:topics"
CACHE_TTL_S = 3600


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _lane_key(network_key: str) -> str:
    return (network_key or "").strip().lower()


def _override_thread_id(network_key: str) -> int | None:
    key = _lane_key(network_key)
    if not key:
        return None
    env_key = f"TBCC_LOOT_ROOM_TOPIC_{key.upper()}"
    raw = (os.getenv(env_key) or "").strip()
    if not raw:
        return None
    try:
        tid = int(raw)
        return tid if tid > 0 else None
    except ValueError:
        return None


def _redis_override_thread_id(network_key: str) -> int | None:
    key = _lane_key(network_key)
    if not key:
        return None
    try:
        raw = (_redis().get(f"{REDIS_PREFIX}:override:{key}") or "").strip()
        if raw:
            tid = int(raw)
            return tid if tid > 0 else None
    except Exception:
        logger.debug("loot room topic override read failed lane=%s", key, exc_info=True)
    return None


def set_loot_room_topic_override(network_key: str, thread_id: int | None) -> int | None:
    """Operator override for one lane's Loot Room subtopic id (Redis)."""
    key = _lane_key(network_key)
    if not key:
        return None
    try:
        r = _redis()
        rk = f"{REDIS_PREFIX}:override:{key}"
        if thread_id is None or int(thread_id) <= 0:
            r.delete(rk)
            return None
        tid = int(thread_id)
        r.set(rk, str(tid))
        return tid
    except Exception:
        logger.debug("loot room topic override write failed lane=%s", key, exc_info=True)
        return None


def _load_cached_live_map() -> dict[str, int]:
    try:
        raw = _redis().get(f"{REDIS_PREFIX}:live_map")
        if not raw:
            return {}
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        out: dict[str, int] = {}
        for k, v in data.items():
            try:
                out[str(k).strip().lower()] = int(v)
            except (TypeError, ValueError):
                continue
        return out
    except Exception:
        logger.debug("loot room live map cache read failed", exc_info=True)
        return {}


def _save_cached_live_map(mapping: dict[str, int]) -> None:
    try:
        _redis().set(
            f"{REDIS_PREFIX}:live_map",
            json.dumps(mapping),
            ex=CACHE_TTL_S,
        )
        _redis().set(f"{REDIS_PREFIX}:live_map_at", str(int(time.time())), ex=CACHE_TTL_S)
    except Exception:
        logger.debug("loot room live map cache write failed", exc_info=True)


def build_live_topic_map(live_topics: list[dict]) -> dict[str, int]:
    """Map network_key → message_thread_id from live Loot Room forum topic titles."""
    out: dict[str, int] = {}
    for row in live_topics or []:
        tid = row.get("id")
        title = str(row.get("title") or "").strip()
        if tid is None or not title:
            continue
        key = match_topic_to_network_key(title)
        if not key:
            continue
        if key not in out:
            out[key] = int(tid)
    return out


def resolve_loot_room_thread_id(
    network_key: str,
    *,
    live_topics: list[dict] | None = None,
) -> tuple[int | None, str]:
    """
    Return (message_thread_id, source).
    source: override | live | redis_cache | static_valid | static_stale | missing
    """
    key = _lane_key(network_key)
    if not key:
        return None, "missing"

    override = _redis_override_thread_id(key) or _override_thread_id(key)
    if override is not None:
        return override, "override"

    live_map: dict[str, int] = {}
    if live_topics is not None:
        live_map = build_live_topic_map(live_topics)
        if live_map:
            _save_cached_live_map(live_map)
    else:
        live_map = _load_cached_live_map()

    if key in live_map:
        return int(live_map[key]), "live" if live_topics is not None else "redis_cache"

    static = main_topic_for_network_key(key)
    if static and live_topics is not None:
        live_ids = {int(t["id"]) for t in live_topics if t.get("id") is not None}
        if int(static.message_thread_id) in live_ids:
            return int(static.message_thread_id), "static_valid"
        logger.warning(
            "Loot Room topic map stale for lane=%s: static id %s not in live group %s",
            key,
            static.message_thread_id,
            MAIN_GROUP_IDENT,
        )
        return None, "static_stale"

    if static:
        return int(static.message_thread_id), "static_valid"

    return None, "missing"


def format_loot_room_topic_status(
    network_key: str,
    *,
    live_topics: list[dict] | None = None,
) -> str:
    tid, source = resolve_loot_room_thread_id(network_key, live_topics=live_topics)
    net = network_channel_by_key(network_key)
    label = net.display_name if net else network_key
    if tid is None:
        return f"{label}: <b>no subtopic</b> ({source})"
    return f"{label}: <code>{tid}</code> ({source})"


def verify_loot_room_topic_map(*, live_topics: list[dict]) -> dict[str, Any]:
    """Compare static map vs live Loot Room topics."""
    live_map = build_live_topic_map(live_topics)
    live_by_id = {int(t["id"]): str(t.get("title") or "") for t in live_topics if t.get("id") is not None}
    rows: list[dict[str, Any]] = []
    for row in AOF_MAIN_GROUP_TOPIC_MAP:
        key = row.network_key
        if not key:
            continue
        tid_live = live_map.get(key)
        static_ok = int(row.message_thread_id) in live_by_id
        rows.append(
            {
                "network_key": key,
                "static_thread_id": row.message_thread_id,
                "static_title": row.topic_title,
                "live_thread_id": tid_live,
                "live_title": live_by_id.get(tid_live) if tid_live else None,
                "static_id_exists_in_group": static_ok,
                "title_match": tid_live == row.message_thread_id if tid_live else False,
            }
        )
    unmapped = [
        {"id": tid, "title": title}
        for tid, title in sorted(live_by_id.items())
        if not match_topic_to_network_key(title)
    ]
    return {"mapped": rows, "unmapped_live_topics": unmapped, "live_topic_count": len(live_by_id)}


async def fetch_live_loot_room_topics(storage) -> list[dict]:
    return await storage.list_forum_topics(MAIN_GROUP_IDENT)
