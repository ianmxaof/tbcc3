"""SCRP folder micro-pull → Storage Hub forum subtopics."""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_scrape_inbound_map import DEFAULT_INBOUND_SOURCES
from app.data.aof_storage_hub_map import CONTENT_LANE_NETWORK_KEYS, STORAGE_HUB_IDENT, storage_map_by_key
from app.services.aof_batch_scrape import _inbound_specs_for_pool, discover_folder_index

logger = logging.getLogger(__name__)

MICRO_PULL_PILOT_LANE = "ass"
MICRO_PULL_INBOX_LANE = "inbox"
MICRO_PULL_DEFAULT_LIMIT = 10
MICRO_PULL_REDIS_KEY = "tbcc:scrape_micro_pull:cursor"
MICRO_PULL_LANE_ROTATION_KEY = "tbcc:scrape_micro_pull:lane_idx"


def micro_pull_enabled() -> bool:
    return (os.getenv("TBCC_SCRAPE_MICRO_PULL_ENABLED") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def micro_pull_limit() -> int:
    raw = (os.getenv("TBCC_SCRAPE_MICRO_PULL_LIMIT") or str(MICRO_PULL_DEFAULT_LIMIT)).strip()
    try:
        return max(1, min(int(raw), 50))
    except ValueError:
        return MICRO_PULL_DEFAULT_LIMIT


def micro_pull_lane() -> str:
    return (os.getenv("TBCC_SCRAPE_MICRO_PULL_LANE") or MICRO_PULL_PILOT_LANE).strip().lower()


def micro_pull_firehose_enabled() -> bool:
    """
    Firehose mode: SCRP BULK → AOF INBOX only (no per-lane topic rotation).
    Set TBCC_SCRAPE_MICRO_PULL_MODE=firehose or TBCC_SCRAPE_FIREHOSE=1.
    """
    mode = (os.getenv("TBCC_SCRAPE_MICRO_PULL_MODE") or "").strip().lower()
    if mode in ("firehose", "inbox", "bulk"):
        return True
    return (os.getenv("TBCC_SCRAPE_FIREHOSE") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def micro_pull_lanes() -> list[str]:
    """
    Lanes rotated by Beat/Celery tick. Default: all content-lane keys with a Storage Hub topic.
    Firehose: inbox only (SCRP BULK → AOF INBOX topic 22569).
    Override: TBCC_SCRAPE_MICRO_PULL_LANES=bop,blowjob,ass (comma-separated).
    """
    if micro_pull_firehose_enabled():
        return ["inbox"] if "inbox" in storage_map_by_key() else []
    raw = (os.getenv("TBCC_SCRAPE_MICRO_PULL_LANES") or "").strip()
    if raw:
        wanted = {x.strip().lower() for x in raw.split(",") if x.strip()}
        return [k for k in sorted(wanted) if k in storage_map_by_key()]
    return sorted(k for k in CONTENT_LANE_NETWORK_KEYS if k in storage_map_by_key())


def pick_micro_pull_lane_for_tick() -> str | None:
    """Round-robin lane selection across micro_pull_lanes()."""
    lanes = micro_pull_lanes()
    if not lanes:
        return None
    if len(lanes) == 1:
        return lanes[0]
    try:
        r = _redis_client()
        n = int(r.incr(MICRO_PULL_LANE_ROTATION_KEY))
        return lanes[(n - 1) % len(lanes)]
    except Exception:
        logger.debug("micro_pull lane rotation fallback", exc_info=True)
        return lanes[0]


def _redis_client():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _pick_source_index(spec_count: int, lane_key: str) -> int:
    if spec_count <= 1:
        return 0
    try:
        r = _redis_client()
        key = f"{MICRO_PULL_REDIS_KEY}:{lane_key}"
        n = int(r.incr(key))
        return (n - 1) % spec_count
    except Exception:
        logger.debug("micro_pull redis cursor unavailable", exc_info=True)
        return 0


def plan_lane_micro_pull(
    db: Session,
    lane_key: str,
    *,
    folder_index: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Resolve SCRP sources + Storage Hub topic for a lane (no Telethon I/O)."""
    key = (lane_key or MICRO_PULL_PILOT_LANE).strip().lower()
    topic_row = storage_map_by_key().get(key)
    if not topic_row:
        return {"ok": False, "reason": "unknown_lane", "lane_key": key}

    specs = _inbound_specs_for_pool(
        key,
        folder_index or {},
        use_folder=True,
        use_defaults=True,
    )
    if not specs and key in DEFAULT_INBOUND_SOURCES:
        specs = [
            {
                "chat_id": int(item["chat_id"]),
                "label": item.get("label") or str(item["chat_id"]),
                "from_folder": None,
            }
            for item in DEFAULT_INBOUND_SOURCES[key]
        ]

    pick_idx = _pick_source_index(len(specs), key) if specs else 0
    picked = specs[pick_idx] if specs else None

    return {
        "ok": bool(specs),
        "lane_key": key,
        "topic_title": topic_row.topic_title,
        "message_thread_id": int(topic_row.message_thread_id),
        "topic_deep_link": f"https://t.me/c/3812457581/{topic_row.message_thread_id}",
        "source_count": len(specs),
        "picked_index": pick_idx,
        "picked_source": picked,
        "sources": specs,
        "limit": micro_pull_limit(),
        "dest_channel": STORAGE_HUB_IDENT,
    }


async def run_lane_micro_pull(
    storage,
    db: Session,
    lane_key: str | None = None,
    *,
    limit: int | None = None,
    folder_index: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """
    Forward up to ``limit`` messages from one SCRP source into the lane Storage Hub subtopic.
    Rotates sources via Redis cursor between runs.
    """
    key = (lane_key or micro_pull_lane()).strip().lower()
    lim = limit if limit is not None else micro_pull_limit()

    if folder_index is None:
        folder_index = await discover_folder_index(storage.client)

    plan = plan_lane_micro_pull(db, key, folder_index=folder_index)
    if not plan.get("ok"):
        return {**plan, "executed": False}

    picked = plan.get("picked_source")
    if not picked:
        return {**plan, "executed": False, "reason": "no_sources"}

    chat_id = int(picked["chat_id"])
    thread_id = int(plan["message_thread_id"])
    result = await storage.forward_channel_to_forum_topic(
        str(chat_id),
        STORAGE_HUB_IDENT,
        thread_id,
        limit=lim,
        media_types="both",
    )

    out = {
        **plan,
        "executed": True,
        "source_chat_id": chat_id,
        "source_label": picked.get("label"),
        "from_folder": picked.get("from_folder"),
        **result,
    }
    logger.info(
        "micro_pull lane=%s source=%s forwarded=%s uploaded=%s",
        key,
        chat_id,
        result.get("forwarded", 0),
        result.get("uploaded", 0),
    )
    return out


async def run_ass_micro_pull(storage, db: Session, *, limit: int | None = None) -> dict[str, Any]:
    """Pilot convenience wrapper — ASS lane only."""
    return await run_lane_micro_pull(storage, db, MICRO_PULL_PILOT_LANE, limit=limit)


async def run_inbox_micro_pull(storage, db: Session, *, limit: int | None = None) -> dict[str, Any]:
    """SCRP BULK folder → AOF INBOX Storage Hub subtopic (uncategorized firehose)."""
    return await run_lane_micro_pull(storage, db, MICRO_PULL_INBOX_LANE, limit=limit)


async def run_micro_pull_tick(storage, db: Session, *, limit: int | None = None) -> dict[str, Any]:
    """Beat tick: firehose inbox pull, or one lane per invocation (round-robin)."""
    if micro_pull_firehose_enabled():
        out = await run_inbox_micro_pull(storage, db, limit=limit)
        out["tick_lane"] = MICRO_PULL_INBOX_LANE
        out["firehose"] = True
        out["lanes_configured"] = micro_pull_lanes()
        return out
    lane = pick_micro_pull_lane_for_tick()
    if not lane:
        return {"ok": True, "skipped": True, "reason": "no_lanes"}
    out = await run_lane_micro_pull(storage, db, lane, limit=limit)
    out["tick_lane"] = lane
    out["lanes_configured"] = micro_pull_lanes()
    return out
