"""Dashboard API: AOF growth hub — bulletin sync, broadcast, storage deposits."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.aof_growth_hub import (
    broadcast_bulletin_to_network,
    growth_hub_status,
    queue_storage_hub_deposits,
    sync_affiliate_network,
    sync_network_album_and_checkout,
    sync_network_schedulers,
)
from app.services.storage_topic_deposit import queue_storage_topic_deposit
from app.services.aof_network_liveness import (
    apply_network_liveness,
    liveness_status,
    liveness_message_thread_id,
    queue_first_subscription_celebration,
)
from app.services.drop_countdown import schedule_drop_countdown
from app.services.feed_rhythm import feed_rhythm_status
from app.services.main_group_notifications import main_group_notify_status
from app.services.aof_topic_mirror import queue_topic_mirror_all, topic_mirror_status
from app.data.aof_main_group_topic_map import main_topic_for_network_key

logger = logging.getLogger(__name__)

router = APIRouter()


class StorageDepositBody(BaseModel):
    limit: int | None = Field(None, ge=1, le=200, description="Per topic; omit for TBCC_STORAGE_POOL_SEED_BATCH default")
    topic_keys: list[str] | None = Field(
        None,
        description="Optional network keys (ai, milf, goon, …). Omit = all matched topics.",
    )
    media_types: str = Field("both", pattern="^(both|photos|videos)$")
    content_lanes_only: bool = Field(
        True,
        description="When true (default), seed content receive lanes only — excludes PACKS storage.",
    )


class StorageDepositTopicBody(BaseModel):
    message_thread_id: int = Field(..., ge=1, description="Storage Hub forum topic id")
    limit: int | None = Field(None, ge=1, le=200, description="Max NEW deduped items; default TBCC_STORAGE_POOL_SEED_BATCH")
    media_types: str = Field("videos", pattern="^(both|photos|videos)$")
    topic_title: str | None = Field(None, description="Optional title hint for fuzzy map")


class TopicMirrorBody(BaseModel):
    limit_per_pair: int = Field(8, ge=1, le=30)
    topic_keys: list[str] | None = None
    media_types: str = Field("both", pattern="^(both|photos|videos)$")


class ScheduleDropBody(BaseModel):
    lane_key: str = Field(..., min_length=2, max_length=64)
    drop_at: datetime = Field(..., description="UTC datetime for the live drop")
    channel_identifier: str | None = None
    message_thread_id: int | None = None
    pool_id: int | None = None


@router.get("/status")
def get_growth_hub_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    return growth_hub_status(db)


@router.post("/apply-stars-bait")
def post_apply_stars_bait(
    post_channel_now: bool = Query(False),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Seed Stars-bait funnel RAG + main-group pacing scheduler."""
    from app.services.stars_bait_outreach import apply_stars_bait_outreach

    report = apply_stars_bait_outreach(db, execute=True, post_channel_now=post_channel_now)
    db.commit()
    return {"ok": True, **report}


@router.post("/apply-mainhub")
def post_apply_mainhub(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Seed @aofmainhub CTA + liveness schedulers (durable pin + ephemeral pings)."""
    from app.services.mainhub_growth import apply_mainhub_growth

    report = apply_mainhub_growth(db, execute=True, post_now=False)
    db.commit()
    return {"ok": True, **report}


@router.post("/sync-schedulers")
def post_sync_schedulers(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Merge links hub bulletin + channel promos into every network scheduler."""
    report = sync_network_schedulers(db, execute=True)
    db.commit()
    return {"ok": True, **report}


@router.post("/sync-affiliate-rotation")
def post_sync_affiliate_rotation(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Rebuild partner bulletin + per-channel sponsor footer rotations from promo_affiliate_links."""
    report = sync_affiliate_network(db, execute=True)
    db.commit()
    return {"ok": True, **report}


@router.post("/sync-album-checkout")
def post_sync_album_checkout(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Set album_size=1 and Stars group-access checkout on all AOF network schedulers + pools."""
    report = sync_network_album_and_checkout(db, execute=True)
    db.commit()
    return {"ok": True, **report}


@router.post("/conversion-sprint")
def post_conversion_sprint(
    post_channel_now: bool = Query(True, description="Queue stars-bait main-group post immediately"),
    broadcast: bool = Query(True, description="Blast links hub bulletin to every network channel"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """One-shot revenue funnel: stars-bait → album checkout → scheduler sync → optional bulletin blast."""
    from app.services.stars_bait_outreach import apply_stars_bait_outreach

    report: dict[str, Any] = {}
    try:
        report["stars_bait"] = apply_stars_bait_outreach(db, execute=True, post_channel_now=post_channel_now)
        report["album_checkout"] = sync_network_album_and_checkout(db, execute=True)
        report["schedulers"] = sync_network_schedulers(db, execute=True)
        if broadcast:
            report["broadcast"] = broadcast_bulletin_to_network(db, pin_main=True)
        db.commit()
        return {"ok": True, **report}
    except Exception as e:
        db.rollback()
        logger.exception("conversion-sprint failed")
        raise HTTPException(status_code=500, detail=str(e)[:300]) from e


@router.post("/broadcast-bulletin")
def post_broadcast_bulletin(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Sync schedulers then post links hub (variation 0) to every channel; pin on main."""
    try:
        return {"ok": True, **broadcast_bulletin_to_network(db, pin_main=True)}
    except Exception as e:
        logger.exception("broadcast-bulletin failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)[:300]) from e


@router.post("/weekly-build-log")
def post_weekly_build_log(
    force: bool = Query(True, description="Queue now (ignore weekday/hour gate)"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Draft + queue PATCH NOTES (Loot Room topic 2408) + @aofmainhub synopsis."""
    from app.services.weekly_build_log import queue_weekly_build_log_posts

    try:
        return {"ok": True, **queue_weekly_build_log_posts(db, force=force)}
    except Exception as e:
        logger.exception("weekly-build-log failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)[:300]) from e


@router.get("/liveness-status")
def get_liveness_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    return liveness_status(db)


@router.post("/apply-liveness")
def post_apply_liveness(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Install faster cadences, main-group pulse posts, drop signals, pool backup posts."""
    try:
        return {"ok": True, **apply_network_liveness(db, execute=True)}
    except Exception as e:
        logger.exception("apply-liveness failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)[:300]) from e


@router.post("/celebrate-first-sub")
def post_celebrate_first_sub(db: Session = Depends(get_db)) -> dict[str, Any]:
    """One-shot main-group celebration for first Stars subscription (idempotent)."""
    try:
        return queue_first_subscription_celebration(db)
    except Exception as e:
        logger.exception("celebrate-first-sub failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)[:300]) from e


@router.post("/storage-deposit")
def post_storage_deposit(body: StorageDepositBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Import media from Storage Hub forum topics into matching AOF channel pools.
    Non-destructive: creates pending import jobs (existing pool media untouched).
    """
    try:
        return queue_storage_hub_deposits(
            db,
            limit=body.limit,
            topic_keys=body.topic_keys,
            media_types=body.media_types,
            content_lanes_only=body.content_lanes_only,
        )
    except Exception as e:
        logger.exception("storage-deposit failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)[:300]) from e


@router.post("/storage-deposit/topic")
def post_storage_deposit_topic(body: StorageDepositTopicBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Deposit from one Storage Hub forum topic into its mapped AOF pool."""
    try:
        return queue_storage_topic_deposit(
            db,
            message_thread_id=body.message_thread_id,
            limit=body.limit,
            topic_title=(body.topic_title or "").strip(),
            media_types=body.media_types,
        )
    except Exception as e:
        logger.exception("storage-deposit/topic failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)[:300]) from e


@router.get("/feed-rhythm")
def get_feed_rhythm_status() -> dict[str, Any]:
    return feed_rhythm_status()


@router.get("/creative-search")
def get_creative_search(
    db: Session = Depends(get_db),
    entry_type: str | None = Query(None),
    surface: str | None = Query(None),
    campaign: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(5, ge=1, le=20),
) -> dict[str, Any]:
    from app.services.creative_rag import search_creative

    rows = search_creative(
        db,
        entry_type=entry_type,
        surface=surface,
        campaign=campaign,
        query=q,
        limit=limit,
    )
    return {
        "ok": True,
        "count": len(rows),
        "items": [
            {
                "id": r.id,
                "entry_type": r.entry_type,
                "campaign": r.campaign,
                "catalog_key": r.catalog_key,
                "title": r.title,
                "prompt_gate_key": r.prompt_gate_key,
                "asset_url": r.asset_url,
            }
            for r in rows
        ],
    }


@router.get("/main-group-notify")
def get_main_group_notify_status() -> dict[str, Any]:
    return main_group_notify_status()


@router.post("/schedule-drop")
def post_schedule_drop(body: ScheduleDropBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Schedule lane drop with edit-in-place countdown (60→45→30→15→5…1→live album)."""
    try:
        drop_at = body.drop_at
        if drop_at.tzinfo is None:
            drop_at = drop_at.replace(tzinfo=timezone.utc)
        thread = body.message_thread_id
        if thread is None:
            mt = main_topic_for_network_key(body.lane_key.strip().lower())
            thread = mt.message_thread_id if mt else liveness_message_thread_id()
        return schedule_drop_countdown(
            db,
            lane_key=body.lane_key.strip().lower(),
            drop_at=drop_at,
            channel_identifier=body.channel_identifier,
            message_thread_id=thread,
            pool_id=body.pool_id,
            execute=True,
        )
    except Exception as e:
        logger.exception("schedule-drop failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)[:300]) from e


@router.get("/topic-mirror")
def get_topic_mirror_route() -> dict[str, Any]:
    return topic_mirror_status()


@router.post("/topic-mirror")
def post_topic_mirror(body: TopicMirrorBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Mirror deduped Storage Hub topic media into matching main supergroup topics."""
    try:
        return queue_topic_mirror_all(
            db,
            limit_per_pair=body.limit_per_pair,
            topic_keys=body.topic_keys,
            media_types=body.media_types,
        )
    except Exception as e:
        logger.exception("topic-mirror failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)[:300]) from e
