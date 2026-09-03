"""Keyword + emoji search over approved AOF media pools."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.data.aof_storage_hub_map import STORAGE_CATEGORY_EMOJI, category_emoji_for_network_key
from app.models.media import Media
from app.services.aof_feed_rhythm_v2 import network_key_for_pool_name
from app.services.aof_lane_tag_map import LANE_TAG_MAP, normalize_tag_token
from app.data.aof_library_forum_topic_map import (
    library_forum_topic_deep_link,
    library_forum_topic_for_network_key,
)
from app.services.aof_search_surfaces import AofSearchSurface, pool_ids_for_surface
from app.services.loot_media_deliverable import filter_roll_candidates

_EMOJI_TO_LANE: dict[str, str] = {
    emoji: key for key, emoji in STORAGE_CATEGORY_EMOJI.items()
}
_TOKEN_RE = re.compile(r"[^\w\u0080-\uFFFF#]+", re.UNICODE)


@dataclass
class ParsedSearchQuery:
    raw: str
    lane_keys: list[str] = field(default_factory=list)
    tag_tokens: list[str] = field(default_factory=list)
    emojis_found: list[str] = field(default_factory=list)


def aof_content_search_enabled() -> bool:
    import os

    return (os.getenv("TBCC_AOF_SEARCH_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def parse_search_query(text: str) -> ParsedSearchQuery:
    raw = (text or "").strip()
    if raw.lower().startswith("/find"):
        raw = raw[5:].strip()
    lane_keys: list[str] = []
    tag_tokens: list[str] = []
    emojis_found: list[str] = []
    remainder = raw

    for emoji, lane in _EMOJI_TO_LANE.items():
        if emoji in remainder:
            emojis_found.append(emoji)
            if lane not in lane_keys:
                lane_keys.append(lane)
            remainder = remainder.replace(emoji, " ")

    for part in _TOKEN_RE.split(remainder):
        token = normalize_tag_token(part)
        if not token or len(token) < 2:
            continue
        mapped = LANE_TAG_MAP.get(token)
        if mapped:
            for lane in mapped:
                if lane not in lane_keys:
                    lane_keys.append(lane)
            continue
        if token.startswith("#"):
            token = token[1:]
        if token and token not in tag_tokens:
            tag_tokens.append(token)

    return ParsedSearchQuery(
        raw=raw,
        lane_keys=lane_keys,
        tag_tokens=tag_tokens,
        emojis_found=emojis_found,
    )


def _pool_ids_for_lanes(db: Session, lane_keys: list[str], surface: AofSearchSurface) -> list[int]:
    from app.models.content_pool import ContentPool

    from app.services.aof_search_surfaces import pool_names_for_lane_keys

    surface_ids = set(pool_ids_for_surface(db, surface))
    if not lane_keys:
        return list(surface_ids)
    names = pool_names_for_lane_keys(frozenset(lane_keys))
    if not names:
        return []
    rows = db.query(ContentPool.id).filter(ContentPool.name.in_(names)).all()
    ids = [int(r[0]) for r in rows]
    return [pid for pid in ids if pid in surface_ids]


def search_approved_media(
    db: Session,
    query: str,
    *,
    surface: AofSearchSurface = "loot_room",
    limit: int = 6,
    pool_ids: list[int] | None = None,
) -> dict[str, Any]:
    parsed = parse_search_query(query)
    if not parsed.raw and not parsed.lane_keys and not parsed.tag_tokens:
        return {
            "ok": False,
            "reason": "empty_query",
            "parsed": parsed,
            "items": [],
            "total_candidates": 0,
        }

    if pool_ids is None:
        if parsed.lane_keys:
            pool_ids = _pool_ids_for_lanes(db, parsed.lane_keys, surface)
        else:
            pool_ids = pool_ids_for_surface(db, surface)

    if not pool_ids:
        return {
            "ok": False,
            "reason": "no_pools_for_surface",
            "parsed": parsed,
            "items": [],
            "total_candidates": 0,
        }

    q = db.query(Media).filter(Media.status == "approved", Media.pool_id.in_(pool_ids))

    if parsed.tag_tokens:
        clauses = [Media.tags.ilike(f"%{tok}%") for tok in parsed.tag_tokens[:8]]
        q = q.filter(or_(*clauses))

    fetch_limit = max(limit * 4, 24)
    rows = q.order_by(Media.id.desc()).limit(fetch_limit).all()
    deliverable = filter_roll_candidates(rows)[:limit]

    primary_lane = parsed.lane_keys[0] if parsed.lane_keys else None
    if not primary_lane and deliverable and deliverable[0].pool_id:
        pname = _pool_name(db, int(deliverable[0].pool_id))
        primary_lane = network_key_for_pool_name(pname)

    library_link = None
    if primary_lane:
        topic = library_forum_topic_for_network_key(primary_lane)
        if topic:
            library_link = library_forum_topic_deep_link(topic.message_thread_id)

    return {
        "ok": bool(deliverable),
        "reason": None if deliverable else "no_matches",
        "parsed": {
            "raw": parsed.raw,
            "lane_keys": parsed.lane_keys,
            "tag_tokens": parsed.tag_tokens,
            "emojis_found": parsed.emojis_found,
        },
        "surface": surface,
        "primary_lane": primary_lane,
        "primary_emoji": category_emoji_for_network_key(primary_lane) if primary_lane else None,
        "library_link": library_link,
        "pool_ids": pool_ids,
        "total_candidates": len(rows),
        "items": [_media_summary(m) for m in deliverable],
    }


def _pool_name(db: Session, pool_id: int) -> str | None:
    from app.models.content_pool import ContentPool

    row = db.query(ContentPool.name).filter(ContentPool.id == int(pool_id)).first()
    return str(row[0]) if row else None


def _media_summary(media: Media) -> dict[str, Any]:
    return {
        "id": int(media.id),
        "pool_id": int(media.pool_id) if media.pool_id else None,
        "media_type": media.media_type,
        "tags": (media.tags or "")[:200],
    }
