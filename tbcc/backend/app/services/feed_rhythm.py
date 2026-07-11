"""Detect monotonous text streaks on Loot Room commons and queue media interjections."""

from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_network import AOF_NETWORK_CHANNELS, MAIN_GROUP_IDENT
from app.models.channel import Channel
from app.models.content_pool import ContentPool
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.aof_growth_hub import build_addlist_footer, gate_urls, queue_post_scheduler

logger = logging.getLogger(__name__)

REDIS_RHYTHM_KEY = "tbcc:feed_rhythm:main"
LIVENESS_PREFIX = "AOF — network liveness"


def feed_rhythm_enabled() -> bool:
    return (os.getenv("TBCC_FEED_RHYTHM_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _monotony_threshold() -> int:
    raw = (os.getenv("TBCC_FEED_RHYTHM_TEXT_STREAK") or "3").strip()
    try:
        return max(2, min(8, int(raw)))
    except ValueError:
        return 3


def _cooldown_minutes() -> int:
    raw = (os.getenv("TBCC_FEED_RHYTHM_COOLDOWN_MIN") or "75").strip()
    try:
        return max(15, min(360, int(raw)))
    except ValueError:
        return 75


def classify_delivery_shape(
    *,
    scheduler_name: str | None,
    had_media: bool,
    caption_html: str | None = None,
) -> str:
    if had_media:
        return "media_album"
    name = (scheduler_name or "").lower()
    if "loot" in name or "bot commands" in name:
        return "bot_card"
    if "listening" in name or "relay" in name or "last.fm" in (caption_html or "").lower():
        return "relay_preview"
    if "<code>" in (caption_html or "").lower():
        return "code_block"
    if LIVENESS_PREFIX.lower() in name or "spotlight" in name or "drop ticker" in name:
        return "text_liveness"
    return "text_rect"


def record_delivery_shape(
    db: Session,
    *,
    channel_identifier: str,
    scheduler_name: str | None,
    had_media: bool,
    caption_html: str | None = None,
) -> dict[str, Any]:
    if not feed_rhythm_enabled():
        return {"ok": True, "skipped": True}
    if str(channel_identifier) != MAIN_GROUP_IDENT:
        return {"ok": True, "skipped": True, "reason": "not_main_group"}

    shape = classify_delivery_shape(
        scheduler_name=scheduler_name,
        had_media=had_media,
        caption_html=caption_html,
    )
    entry = {
        "shape": shape,
        "scheduler": (scheduler_name or "")[:80],
        "at": datetime.utcnow().isoformat() + "Z",
    }
    try:
        r = _redis()
        raw = r.get(REDIS_RHYTHM_KEY)
        hist: list[dict] = json.loads(raw) if raw else []
        hist.append(entry)
        hist = hist[-12:]
        r.set(REDIS_RHYTHM_KEY, json.dumps(hist), ex=86400 * 3)
    except Exception as e:
        logger.debug("feed rhythm record: %s", e)
        return {"ok": False, "error": str(e)[:200]}

    streak = 0
    for item in reversed(hist):
        if item.get("shape") in ("text_rect", "text_liveness"):
            streak += 1
        else:
            break

    if streak >= _monotony_threshold():
        return maybe_queue_rhythm_interjection(db, streak=streak)
    return {"ok": True, "shape": shape, "streak": streak}


def maybe_queue_rhythm_interjection(db: Session, *, streak: int) -> dict[str, Any]:
    cooldown_key = f"{REDIS_RHYTHM_KEY}:last_interject"
    try:
        r = _redis()
        last = r.get(cooldown_key)
        if last:
            try:
                last_dt = datetime.fromisoformat(last.replace("Z", ""))
                if datetime.utcnow() - last_dt < timedelta(minutes=_cooldown_minutes()):
                    return {"ok": True, "skipped": True, "reason": "cooldown", "streak": streak}
            except ValueError:
                pass
    except Exception:
        pass

    main = db.query(Channel).filter(Channel.identifier == MAIN_GROUP_IDENT).first()
    if not main:
        return {"ok": False, "error": "main_group_missing"}

    pools = [
        db.query(ContentPool).filter(ContentPool.name == nc.pool_name).first()
        for nc in AOF_NETWORK_CHANNELS
        if nc.key not in ("main", "packs")
    ]
    pools = [p for p in pools if p and p.id]
    if not pools:
        return {"ok": False, "error": "no_pools"}

    pool = random.choice(pools)
    lv = gate_urls(db)
    footer = build_addlist_footer(lv)
    lane = next((nc for nc in AOF_NETWORK_CHANNELS if nc.pool_name == pool.name), None)
    lane_name = lane.display_name if lane else pool.name

    from app.services.aof_main_group_copy import feed_rhythm_interjection_body
    from app.services.aof_feed_rhythm_v2 import main_group_album_size, vip_roll_tease_line

    body = (
        f"{feed_rhythm_interjection_body(lane_name, '')}\n"
        f"{vip_roll_tease_line(lane_name, public_size=main_group_album_size())}"
        f"{footer}"
    )

    sched = ScheduledTextPost(
        name="AOF — feed rhythm interjection",
        channel_id=main.id,
        content=body,
        pool_collective_random=True,
        album_size=main_group_album_size(),
        pool_randomize=True,
        send_silent=True,
        created_at=datetime.utcnow(),
    )
    from app.services.aof_growth_hub import (
        _apply_scheduler_album_checkout,
        checkout_button_label_for_plan,
        resolve_group_access_plan_id,
    )

    plan_id = resolve_group_access_plan_id(db)
    _apply_scheduler_album_checkout(
        sched,
        pool,
        db,
        plan_id=plan_id,
        button_label=checkout_button_label_for_plan(db, plan_id),
        preserve_album_size=True,
    )
    from app.services.aof_feed_rhythm_v2 import apply_main_group_tease_media

    apply_main_group_tease_media(sched)
    db.add(sched)
    db.commit()

    queued = queue_post_scheduler(int(sched.id), countdown=30)
    try:
        r = _redis()
        r.set(cooldown_key, datetime.utcnow().isoformat() + "Z", ex=86400)
        r.set(REDIS_RHYTHM_KEY, json.dumps([]), ex=86400 * 3)
    except Exception:
        pass

    logger.info("feed rhythm interjection queued pool=%s streak=%s", pool.name, streak)
    return {"ok": True, "interjection": True, "pool": pool.name, "streak": streak, **queued}


def feed_rhythm_status() -> dict[str, Any]:
    try:
        r = _redis()
        raw = r.get(REDIS_RHYTHM_KEY)
        hist = json.loads(raw) if raw else []
        last = r.get(f"{REDIS_RHYTHM_KEY}:last_interject")
    except Exception:
        hist = []
        last = None
    return {
        "enabled": feed_rhythm_enabled(),
        "threshold": _monotony_threshold(),
        "cooldown_min": _cooldown_minutes(),
        "recent": hist[-8:],
        "last_interjection_at": last,
    }
