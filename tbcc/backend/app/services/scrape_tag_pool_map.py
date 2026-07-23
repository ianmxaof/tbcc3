"""
Quick hashtag → AOF pool-key suggestions (no CLIP / NSFW / LLM).

Delegates to ``aof_lane_tag_map`` (canonical ``big_tits`` keys). Enable multi-pool
robocopy later with TBCC_SCRAPE_HASHTAG_ROUTE=1.
"""

from __future__ import annotations

from app.services.aof_lane_tag_map import (
    LANE_TAG_MAP,
    normalize_tag_token,
    suggest_lane_keys_from_tags,
)

# Back-compat alias — same map, canonical aof_network keys
HASHTAG_POOL_MAP = LANE_TAG_MAP


def suggest_pool_keys_from_hashtags(tags: str | list[str] | None, *, limit: int = 6) -> list[str]:
    """Return ordered unique AOF pool keys suggested by hashtag sample."""
    return suggest_lane_keys_from_tags(tags, limit=limit)


def suggest_pool_keys_csv(tags: str | list[str] | None) -> str | None:
    keys = suggest_pool_keys_from_hashtags(tags)
    return ",".join(keys) if keys else None


__all__ = [
    "HASHTAG_POOL_MAP",
    "normalize_tag_token",
    "suggest_pool_keys_from_hashtags",
    "suggest_pool_keys_csv",
]
