"""
Content performance pipeline — delivery ledger, Telethon view polling, time-of-day aggregates.

Telegram channel posts expose view counts via Telethon (message.views / GetMessagesViewsRequest).
Those are the same numbers shown next to the eye icon in the Telegram client.
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.channel import Channel
from app.models.post_delivery_metric import PostDeliveryMetric
from app.models.post_outbound_event import PostOutboundEvent
from app.models.scheduled_text_post import ScheduledTextPost

logger = logging.getLogger(__name__)

# Reddit/community heuristic for US-tier-1 audiences (ET). Used as reference bands only.
SUGGESTED_PEAK_HOURS_ET: tuple[tuple[int, int], ...] = ((11, 16), (19, 25))  # 25 => 1am next day


def analytics_timezone() -> ZoneInfo:
    raw = (os.getenv("TBCC_ANALYTICS_TZ") or "America/New_York").strip()
    try:
        return ZoneInfo(raw)
    except Exception:
        return ZoneInfo("America/New_York")


def analytics_timezone_label() -> str:
    return (os.getenv("TBCC_ANALYTICS_TZ") or "America/New_York").strip()


def performance_enabled() -> bool:
    return (os.getenv("TBCC_CONTENT_PERFORMANCE_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def view_refresh_lookback_days() -> int:
    raw = (os.getenv("TBCC_VIEW_REFRESH_LOOKBACK_DAYS") or "14").strip()
    try:
        return max(1, min(90, int(raw)))
    except ValueError:
        return 14


def view_refresh_telegram_session() -> str:
    """Dedicated Telethon session for view polls (avoids poster session lock storms)."""
    raw = (os.getenv("TBCC_VIEW_REFRESH_TELEGRAM_SESSION") or "").strip()
    if raw:
        return raw
    return (os.getenv("TBCC_POSTER_TELEGRAM_SESSION") or "admin_poster").strip()


@dataclass
class ScheduledSendOutcome:
    scheduled_post_id: int
    channel_id: int
    caption_slot_index: int
    caption_variation_count: int
    telegram_message_id: int | None
    telegram_message_ids: list[int]
    scheduler_name: str | None = None
    pack_modifier_id: int | None = None


def _utc_now() -> datetime:
    return datetime.utcnow()


def _hour_buckets(when: datetime | None = None) -> tuple[int, int, str]:
    when = when or _utc_now()
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    tz = analytics_timezone()
    local = when.astimezone(tz)
    return when.hour, local.hour, analytics_timezone_label()


def message_ids_from_send(result) -> list[int]:
    if result is None:
        return []
    if isinstance(result, list):
        return [int(m.id) for m in result if m and getattr(m, "id", None)]
    if getattr(result, "id", None):
        return [int(result.id)]
    return []


def build_scheduled_send_outcome(
    post: ScheduledTextPost,
    sent_result,
    *,
    slot_index: int,
    pack_modifier_id: int | None = None,
) -> ScheduledSendOutcome:
    variations = post.get_content_variations()
    var_count = max(1, len(variations)) if variations else 1
    slot = int(slot_index)
    msg_ids = message_ids_from_send(sent_result)
    post_id = getattr(post, "id", None)
    ch_id = getattr(post, "channel_id", None)
    return ScheduledSendOutcome(
        scheduled_post_id=int(post_id) if post_id is not None else 0,
        channel_id=int(ch_id) if ch_id is not None else 0,
        caption_slot_index=slot,
        caption_variation_count=var_count,
        telegram_message_id=msg_ids[0] if msg_ids else None,
        telegram_message_ids=msg_ids,
        scheduler_name=(post.name or "").strip() or None,
        pack_modifier_id=pack_modifier_id,
    )


def record_post_delivery_metric(
    db: Session,
    *,
    outbound_event: PostOutboundEvent | None,
    event_type: str,
    channel: Channel | None,
    scheduled_post_id: int | None = None,
    pool_id: int | None = None,
    scheduler_name: str | None = None,
    outcome: ScheduledSendOutcome | None = None,
    telegram_message_id: int | None = None,
    telegram_message_ids: list[int] | None = None,
    caption_slot_index: int | None = None,
    caption_variation_count: int | None = None,
    created_at: datetime | None = None,
) -> PostDeliveryMetric | None:
    if not performance_enabled():
        return None

    when = created_at or _utc_now()
    hour_utc, hour_local, tz_label = _hour_buckets(when.replace(tzinfo=timezone.utc))

    if outcome:
        scheduled_post_id = outcome.scheduled_post_id
        caption_slot_index = outcome.caption_slot_index
        caption_variation_count = outcome.caption_variation_count
        scheduler_name = outcome.scheduler_name or scheduler_name
        telegram_message_id = outcome.telegram_message_id
        telegram_message_ids = outcome.telegram_message_ids
        channel_id = outcome.channel_id
    else:
        channel_id = channel.id if channel else None

    ident = None
    if channel:
        ident = (channel.identifier or channel.name or "").strip() or None

    msg_ids = telegram_message_ids or []
    row = PostDeliveryMetric(
        created_at=when,
        post_outbound_event_id=outbound_event.id if outbound_event else None,
        event_type=event_type,
        channel_id=channel_id,
        scheduled_post_id=scheduled_post_id,
        pool_id=pool_id,
        scheduler_name=scheduler_name,
        channel_identifier=ident,
        telegram_message_id=telegram_message_id,
        telegram_message_ids_json=json.dumps(msg_ids) if msg_ids else None,
        caption_slot_index=caption_slot_index,
        caption_variation_count=caption_variation_count,
        posted_hour_utc=hour_utc,
        posted_hour_local=hour_local,
        timezone_label=tz_label,
    )
    db.add(row)
    db.flush()
    return row


def _apply_view_update(row: PostDeliveryMetric, views: int | None, forwards: int | None) -> bool:
    if views is None and forwards is None:
        return False
    changed = False
    if views is not None:
        row.views_latest = int(views)
        peak = int(row.views_peak or 0)
        if int(views) > peak:
            row.views_peak = int(views)
        changed = True
    if forwards is not None:
        row.forwards_latest = int(forwards)
        changed = True
    if changed:
        row.views_updated_at = _utc_now()
    return changed


async def _fetch_views_for_channel(
    client,
    channel_identifier: str,
    message_ids: list[int],
) -> dict[int, dict[str, int | None]]:
    from telethon.tl.functions.messages import GetMessagesViewsRequest

    ident = (channel_identifier or "").strip()
    if not ident or not message_ids:
        return {}

    entity = await client.get_entity(ident)
    ids = sorted({int(i) for i in message_ids if i})
    views_map: dict[int, int | None] = {}
    forwards_map: dict[int, int | None] = {}

    try:
        res = await client(GetMessagesViewsRequest(peer=entity, id=ids, increment=False))
        for mid, vc in zip(ids, getattr(res, "views", []) or []):
            views_map[int(mid)] = int(vc) if vc is not None else None
    except Exception as e:
        logger.info("GetMessagesViews batch failed for %s: %s", ident, e)

    msgs = await client.get_messages(entity, ids=ids)
    for m in msgs or []:
        if not m or not m.id:
            continue
        mid = int(m.id)
        if mid not in views_map or views_map[mid] is None:
            views_map[mid] = getattr(m, "views", None)
        forwards_map[mid] = getattr(m, "forwards", None)

    out: dict[int, dict[str, int | None]] = {}
    for mid in ids:
        out[mid] = {
            "views": views_map.get(mid),
            "forwards": forwards_map.get(mid),
        }
    return out


async def refresh_delivery_views_async(db: Session, *, limit: int = 200) -> dict[str, Any]:
    from telethon import TelegramClient

    from app.services.telethon_session_lock import poster_session_redis_lock
    from app.services.telegram_channel_stats import telethon_stats_configured
    from app.utils.telethon_session import configure_telethon_sqlite_session, prepare_session_sqlite_file

    if not telethon_stats_configured():
        return {"ok": False, "error": "Telethon not configured", "updated": 0}

    since = _utc_now() - timedelta(days=view_refresh_lookback_days())
    rows = (
        db.query(PostDeliveryMetric)
        .filter(
            PostDeliveryMetric.created_at >= since,
            PostDeliveryMetric.telegram_message_id.isnot(None),
            PostDeliveryMetric.channel_identifier.isnot(None),
        )
        .order_by(PostDeliveryMetric.id.desc())
        .limit(max(1, min(500, limit)))
        .all()
    )
    if not rows:
        return {"ok": True, "updated": 0, "checked": 0}

    by_channel: dict[str, list[PostDeliveryMetric]] = defaultdict(list)
    for r in rows:
        ident = (r.channel_identifier or "").strip()
        if ident:
            by_channel[ident].append(r)

    session = view_refresh_telegram_session()
    prepare_session_sqlite_file(session)
    updated = 0
    checked = 0

    with poster_session_redis_lock():
        client = TelegramClient(session, int(os.environ["API_ID"]), os.environ["API_HASH"])
        await client.connect()
        configure_telethon_sqlite_session(client)
        if not await client.is_user_authorized():
            await client.disconnect()
            return {"ok": False, "error": "Telethon session not authorized", "updated": 0}

        try:
            for ident, channel_rows in by_channel.items():
                msg_ids = [int(r.telegram_message_id) for r in channel_rows if r.telegram_message_id]
                try:
                    stats = await _fetch_views_for_channel(client, ident, msg_ids)
                except Exception as e:
                    logger.warning("refresh views for %s: %s", ident, e)
                    continue
                for row in channel_rows:
                    mid = int(row.telegram_message_id or 0)
                    if not mid:
                        continue
                    checked += 1
                    snap = stats.get(mid) or {}
                    if _apply_view_update(row, snap.get("views"), snap.get("forwards")):
                        updated += 1
            db.commit()
        finally:
            await client.disconnect()

    return {"ok": True, "updated": updated, "checked": checked, "channels": len(by_channel)}


def refresh_delivery_views_sync(db: Session, *, limit: int = 200) -> dict[str, Any]:
    import asyncio

    return asyncio.run(refresh_delivery_views_async(db, limit=limit))


def list_delivery_metrics(
    db: Session,
    *,
    days: int = 30,
    limit: int = 100,
    offset: int = 0,
    scheduled_post_id: int | None = None,
    channel_id: int | None = None,
) -> dict[str, Any]:
    since = _utc_now() - timedelta(days=max(1, min(366, days)))
    q = db.query(PostDeliveryMetric).filter(PostDeliveryMetric.created_at >= since)
    if scheduled_post_id is not None:
        q = q.filter(PostDeliveryMetric.scheduled_post_id == int(scheduled_post_id))
    if channel_id is not None:
        q = q.filter(PostDeliveryMetric.channel_id == int(channel_id))
    total = q.count()
    rows = q.order_by(PostDeliveryMetric.id.desc()).offset(offset).limit(max(1, min(500, limit))).all()

    ch_ids = {r.channel_id for r in rows if r.channel_id}
    ch_names: dict[int, str] = {}
    if ch_ids:
        for c in db.query(Channel).filter(Channel.id.in_(ch_ids)).all():
            ch_names[c.id] = c.name or c.identifier or str(c.id)

    items = []
    for r in rows:
        items.append(
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
                "event_type": r.event_type,
                "channel_id": r.channel_id,
                "channel_name": ch_names.get(r.channel_id) if r.channel_id else None,
                "scheduled_post_id": r.scheduled_post_id,
                "pool_id": r.pool_id,
                "scheduler_name": r.scheduler_name,
                "telegram_message_id": int(r.telegram_message_id) if r.telegram_message_id else None,
                "caption_slot_index": r.caption_slot_index,
                "caption_variation_count": r.caption_variation_count,
                "posted_hour_utc": r.posted_hour_utc,
                "posted_hour_local": r.posted_hour_local,
                "timezone_label": r.timezone_label,
                "views_latest": r.views_latest,
                "views_peak": r.views_peak,
                "forwards_latest": r.forwards_latest,
                "views_updated_at": r.views_updated_at.isoformat() + "Z" if r.views_updated_at else None,
            }
        )
    return {
        "range_days": days,
        "total": total,
        "limit": limit,
        "offset": offset,
        "timezone": analytics_timezone_label(),
        "items": items,
    }


def aggregate_views_by_hour(db: Session, *, days: int = 30) -> dict[str, Any]:
    since = _utc_now() - timedelta(days=max(1, min(366, days)))
    rows = (
        db.query(PostDeliveryMetric)
        .filter(
            PostDeliveryMetric.created_at >= since,
            PostDeliveryMetric.views_latest.isnot(None),
            PostDeliveryMetric.posted_hour_local.isnot(None),
        )
        .all()
    )

    by_hour: dict[int, list[int]] = defaultdict(list)
    by_hour_posts: dict[int, int] = defaultdict(int)
    for r in rows:
        h = int(r.posted_hour_local or 0)
        by_hour[h].append(int(r.views_latest or 0))
        by_hour_posts[h] += 1

    hour_rows = []
    for h in range(24):
        vals = by_hour.get(h) or []
        hour_rows.append(
            {
                "hour_local": h,
                "post_count": by_hour_posts.get(h, 0),
                "avg_views": round(sum(vals) / len(vals), 1) if vals else None,
                "total_views": sum(vals) if vals else 0,
                "max_views": max(vals) if vals else None,
            }
        )

    ranked = sorted(
        [x for x in hour_rows if x["avg_views"] is not None],
        key=lambda x: (-float(x["avg_views"]), -int(x["post_count"])),
    )
    top_hours = [x["hour_local"] for x in ranked[:5]]

    return {
        "range_days": days,
        "timezone": analytics_timezone_label(),
        "by_hour": hour_rows,
        "top_hours_local": top_hours,
        "suggested_peak_hours_et": [{"start": s, "end": e % 24} for s, e in SUGGESTED_PEAK_HOURS_ET],
        "note": (
            "posted_hour_local uses TBCC_ANALYTICS_TZ. suggested_peak_hours_et is a community heuristic "
            "(11am–4pm and 7pm–1am US Eastern); top_hours_local is from your own delivery view data."
        ),
    }


def aggregate_views_by_caption_slot(
    db: Session,
    *,
    scheduled_post_id: int,
    days: int = 90,
) -> dict[str, Any]:
    since = _utc_now() - timedelta(days=max(1, min(366, days)))
    rows = (
        db.query(PostDeliveryMetric)
        .filter(
            PostDeliveryMetric.scheduled_post_id == int(scheduled_post_id),
            PostDeliveryMetric.created_at >= since,
        )
        .all()
    )
    post = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == int(scheduled_post_id)).first()
    if not post:
        return {"error": "scheduled post not found"}

    by_slot: dict[int, list[int]] = defaultdict(list)
    sends_by_slot: dict[int, int] = defaultdict(int)
    for r in rows:
        slot = int(r.caption_slot_index or 0)
        sends_by_slot[slot] += 1
        if r.views_latest is not None:
            by_slot[slot].append(int(r.views_latest))

    slots = []
    var_count = max(1, len(post.get_content_variations()) if post.get_content_variations() else 1)
    for slot in range(var_count):
        vals = by_slot.get(slot) or []
        slots.append(
            {
                "caption_slot_index": slot,
                "send_count": sends_by_slot.get(slot, 0),
                "avg_views": round(sum(vals) / len(vals), 1) if vals else None,
                "max_views": max(vals) if vals else None,
                "sample_views": vals[:10],
            }
        )

    return {
        "scheduled_post_id": int(scheduled_post_id),
        "scheduler_name": post.name,
        "range_days": days,
        "caption_variation_count": var_count,
        "slots": slots,
    }


def latest_delivery_for_attribution(db: Session, *, lookback_hours: int = 6) -> PostDeliveryMetric | None:
    since = _utc_now() - timedelta(hours=max(1, min(168, lookback_hours)))
    return (
        db.query(PostDeliveryMetric)
        .filter(PostDeliveryMetric.created_at >= since)
        .order_by(PostDeliveryMetric.id.desc())
        .first()
    )
