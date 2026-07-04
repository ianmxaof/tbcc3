"""Mirror deduped media Storage Hub topic → matching main supergroup topic."""

from __future__ import annotations

import json
import logging
import os
import random
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_network import MAIN_GROUP_IDENT
from app.data.aof_storage_hub_map import AOF_STORAGE_TOPIC_MAP, STORAGE_HUB_IDENT
from app.data.aof_main_group_topic_map import liveness_topic_pool, main_topic_for_network_key

logger = logging.getLogger(__name__)

REDIS_MIRROR_PREFIX = "tbcc:topic_mirror:src"


def topic_mirror_enabled() -> bool:
    return (os.getenv("TBCC_TOPIC_MIRROR_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def deposit_topic_mirror_enabled() -> bool:
    """Separate kill switch for /deposit → main-group mirror (reduces Telethon storms)."""
    if not topic_mirror_enabled():
        return False
    return (os.getenv("TBCC_DEPOSIT_TOPIC_MIRROR") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def liveness_random_topics_enabled() -> bool:
    return (os.getenv("TBCC_LIVENESS_RANDOM_TOPICS") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _mirror_redis_key(storage_thread_id: int, source_message_id: int) -> str:
    return f"{REDIS_MIRROR_PREFIX}:{storage_thread_id}:{source_message_id}"


def is_message_already_mirrored(storage_thread_id: int, source_message_id: int) -> bool:
    try:
        r = _redis()
        return bool(r.get(_mirror_redis_key(storage_thread_id, source_message_id)))
    except Exception:
        return False


def mark_message_mirrored(storage_thread_id: int, source_message_id: int) -> None:
    try:
        r = _redis()
        r.set(_mirror_redis_key(storage_thread_id, source_message_id), "1", ex=86400 * 90)
    except Exception as e:
        logger.debug("topic mirror redis mark: %s", e)


def pick_random_liveness_topic_id(*, seed: str | None = None) -> int | None:
    pool = liveness_topic_pool()
    if not pool:
        return None
    if seed:
        idx = hash(seed) % len(pool)
        return int(pool[idx].message_thread_id)
    return int(random.choice(pool).message_thread_id)


def resolve_liveness_thread_for_send(
    post_name: str | None,
    *,
    scheduled_thread_id: int | None = None,
    rotation_index: int | None = None,
) -> int | None:
    """
    Per-send forum topic for liveness schedulers.
    Random lane topic when enabled; optional fixed TBCC_LIVENESS_MESSAGE_THREAD_ID override.
    """
    from app.services.aof_network_liveness import LIVENESS_PREFIX, liveness_message_thread_id

    name = (post_name or "").strip()
    if LIVENESS_PREFIX not in name:
        return scheduled_thread_id

    fixed = liveness_message_thread_id()
    if fixed is not None and not liveness_random_topics_enabled():
        return fixed

    if liveness_random_topics_enabled():
        seed = f"{name}:{rotation_index or 0}"
        picked = pick_random_liveness_topic_id(seed=seed)
        if picked:
            return picked
    return scheduled_thread_id or fixed


async def mirror_storage_topic_to_main_async(
    storage_thread_id: int,
    main_thread_id: int,
    *,
    limit: int = 8,
    media_types: str = "both",
    prefer_import_session: bool = False,
    lock_timeout_s: float | None = None,
) -> dict[str, int]:
    from app.services.telegram_admin import run_telegram_import_io, run_telegram_io
    from app.services.telegram_storage import TelegramStorage

    async def go(storage: TelegramStorage):
        return await storage.forward_storage_topic_to_main_topic(
            STORAGE_HUB_IDENT,
            int(storage_thread_id),
            MAIN_GROUP_IDENT,
            int(main_thread_id),
            limit=limit,
            media_types=media_types,
            is_already_mirrored=is_message_already_mirrored,
            on_mirrored=mark_message_mirrored,
        )

    runner = run_telegram_import_io if prefer_import_session else run_telegram_io
    return await runner(go, lock_timeout_s=lock_timeout_s)


def mirror_storage_topic_to_main_sync(
    storage_thread_id: int,
    main_thread_id: int,
    *,
    limit: int = 8,
    media_types: str = "both",
    prefer_import_session: bool = False,
    use_worker_loop: bool = False,
    lock_timeout_s: float | None = None,
) -> dict[str, int]:
    import asyncio

    from app.services.import_job_runner import _run_on_worker_loop

    coro = mirror_storage_topic_to_main_async(
        storage_thread_id,
        main_thread_id,
        limit=limit,
        media_types=media_types,
        prefer_import_session=prefer_import_session,
        lock_timeout_s=lock_timeout_s,
    )
    if use_worker_loop:
        return _run_on_worker_loop(coro)
    return asyncio.run(coro)


def queue_topic_mirror_all(
    db: Session,
    *,
    limit_per_pair: int = 8,
    topic_keys: list[str] | None = None,
    media_types: str = "both",
    initial_countdown: int = 0,
) -> dict[str, Any]:
    """Queue Celery jobs: each storage lane → matching main supergroup topic."""
    from app.workers.topic_mirror_worker import mirror_topic_pair

    if not topic_mirror_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    allow = {k.strip().lower() for k in (topic_keys or []) if k.strip()}
    jobs: list[dict] = []
    stagger = 0
    for storage_row in AOF_STORAGE_TOPIC_MAP:
        if allow and storage_row.network_key not in allow:
            continue
        main_row = main_topic_for_network_key(storage_row.network_key)
        if not main_row:
            jobs.append(
                {
                    "network_key": storage_row.network_key,
                    "storage_topic": storage_row.topic_title,
                    "status": "no_main_topic",
                }
            )
            continue
        result = mirror_topic_pair.apply_async(
            args=[
                int(storage_row.message_thread_id),
                int(main_row.message_thread_id),
            ],
            kwargs={"limit": limit_per_pair, "media_types": media_types},
            countdown=max(0, int(initial_countdown)) + stagger * 25,
        )
        stagger += 1
        jobs.append(
            {
                "network_key": storage_row.network_key,
                "storage_topic": storage_row.topic_title,
                "storage_thread_id": storage_row.message_thread_id,
                "main_topic": main_row.topic_title,
                "main_thread_id": main_row.message_thread_id,
                "task_id": result.id,
                "status": "queued",
            }
        )
    return {"ok": True, "limit_per_pair": limit_per_pair, "jobs": jobs, "matched_count": len(jobs)}


def topic_mirror_status() -> dict[str, Any]:
    pairs = []
    for s in AOF_STORAGE_TOPIC_MAP:
        m = main_topic_for_network_key(s.network_key)
        pairs.append(
            {
                "network_key": s.network_key,
                "storage_title": s.topic_title,
                "storage_thread_id": s.message_thread_id,
                "main_title": m.topic_title if m else None,
                "main_thread_id": m.message_thread_id if m else None,
                "paired": m is not None,
            }
        )
    return {
        "enabled": topic_mirror_enabled(),
        "liveness_random_topics": liveness_random_topics_enabled(),
        "pairs": pairs,
    }
