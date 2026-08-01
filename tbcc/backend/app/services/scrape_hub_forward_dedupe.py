"""Dedupe SCRP micro-pull forwards into Storage Hub forum topics."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

REDIS_HUB_FORWARD_PREFIX = "tbcc:hub_fwd"
DEFAULT_TTL_SECONDS = 86400 * 90


def hub_forward_dedupe_enabled() -> bool:
    return (os.getenv("TBCC_SCRAPE_MICRO_PULL_DEDUPE") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def hub_forward_redis_key(dest_thread_id: int, source_chat_id: int, source_message_id: int) -> str:
    return f"{REDIS_HUB_FORWARD_PREFIX}:{int(dest_thread_id)}:{int(source_chat_id)}:{int(source_message_id)}"


def is_hub_forward_duplicate(
    dest_thread_id: int,
    source_chat_id: int,
    source_message_id: int,
) -> bool:
    if not hub_forward_dedupe_enabled():
        return False
    try:
        return bool(_redis().get(hub_forward_redis_key(dest_thread_id, source_chat_id, source_message_id)))
    except Exception:
        logger.debug("hub forward dedupe read failed", exc_info=True)
        return False


def mark_hub_forward_done(
    dest_thread_id: int,
    source_chat_id: int,
    source_message_id: int,
    *,
    ttl_seconds: int | None = None,
) -> None:
    if not hub_forward_dedupe_enabled():
        return
    ttl = int(ttl_seconds or DEFAULT_TTL_SECONDS)
    try:
        _redis().set(
            hub_forward_redis_key(dest_thread_id, source_chat_id, source_message_id),
            "1",
            ex=max(3600, ttl),
        )
    except Exception:
        logger.debug("hub forward dedupe mark failed", exc_info=True)
