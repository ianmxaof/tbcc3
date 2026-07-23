"""Per-lane approved media depth vs Loot Room subtopic readiness thresholds."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.data.aof_network import AOF_NETWORK_CHANNELS
from app.data.loot_lane_economy import (
    CHANNEL_READINESS,
    LANE_TOPIC_ELIGIBLE_KEYS,
    lane_at_target_median,
    lane_display_name,
    lane_ready_for_loot_subtopic,
)
from app.models.content_pool import ContentPool
from app.models.media import Media


def _photo_video_counts(db: Session, pool_id: int) -> tuple[int, int]:
    photos = (
        db.query(func.count(Media.id))
        .filter(Media.pool_id == pool_id, Media.status == "approved", Media.media_type == "photo")
        .scalar()
        or 0
    )
    videos = (
        db.query(func.count(Media.id))
        .filter(Media.pool_id == pool_id, Media.status == "approved", Media.media_type == "video")
        .scalar()
        or 0
    )
    return int(photos), int(videos)


def audit_lane_readiness(db: Session) -> dict[str, Any]:
    """Return per-lane approved photo/video depth and readiness vs CHANNEL_READINESS."""
    rows: list[dict[str, Any]] = []
    ready = 0
    near_median = 0
    for ch in AOF_NETWORK_CHANNELS:
        if ch.key not in LANE_TOPIC_ELIGIBLE_KEYS:
            continue
        pool = db.query(ContentPool).filter(ContentPool.name == ch.pool_name).first()
        images = videos = 0
        pool_id = None
        if pool:
            pool_id = int(pool.id)
            images, videos = _photo_video_counts(db, pool_id)
        is_ready = lane_ready_for_loot_subtopic(images=images, videos=videos)
        at_median = lane_at_target_median(images=images, videos=videos)
        if is_ready:
            ready += 1
        if at_median:
            near_median += 1
        img_gap = max(0, CHANNEL_READINESS.target_median_images - images)
        vid_gap = max(0, CHANNEL_READINESS.target_median_videos - videos)
        rows.append(
            {
                "network_key": ch.key,
                "display_name": lane_display_name(ch.key),
                "pool_name": ch.pool_name,
                "pool_id": pool_id,
                "images": images,
                "videos": videos,
                "ready_for_subtopic": is_ready,
                "at_target_median": at_median,
                "gap_to_median_images": img_gap,
                "gap_to_median_videos": vid_gap,
                "scrape_priority": img_gap + vid_gap,
            }
        )
    rows.sort(key=lambda r: (-int(r["scrape_priority"]), r["network_key"]))
    return {
        "ok": True,
        "thresholds": {
            "min_images": CHANNEL_READINESS.min_images,
            "min_videos": CHANNEL_READINESS.min_videos,
            "target_median_images": CHANNEL_READINESS.target_median_images,
            "target_median_videos": CHANNEL_READINESS.target_median_videos,
            "aspirational": CHANNEL_READINESS.aspirational_per_format,
        },
        "lanes_eligible": len(rows),
        "lanes_ready_for_subtopic": ready,
        "lanes_at_target_median": near_median,
        "lanes": rows,
    }
