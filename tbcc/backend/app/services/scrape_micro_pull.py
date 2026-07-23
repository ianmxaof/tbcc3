"""SCRP folder micro-pull → Storage Hub forum subtopics (pilot: ASS)."""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_scrape_inbound_map import DEFAULT_INBOUND_SOURCES
from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT, storage_map_by_key
from app.services.aof_batch_scrape import _inbound_specs_for_pool, discover_folder_index

logger = logging.getLogger(__name__)

MICRO_PULL_PILOT_LANE = "ass"
MICRO_PULL_DEFAULT_LIMIT = 10
MICRO_PULL_REDIS_KEY = "tbcc:scrape_micro_pull:cursor"


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
