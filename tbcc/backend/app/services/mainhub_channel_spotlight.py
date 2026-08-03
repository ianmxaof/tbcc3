"""Daily @aofmainhub channel spotlight — window-shop promo with SFW teaser album."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_network import (
    MAINHUB_CHANNEL_IDENT,
    MAINHUB_RAW,
    SFW_X_PROMO_POOL_NAME,
    network_channel_by_key,
)
from app.models.channel import Channel
from app.models.content_pool import ContentPool
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.aof_growth_hub import build_addlist_footer, lv_urls, queue_post_scheduler
from app.services.lane_of_the_day import (
    SPOTLIGHT_HOOKS,
    eligible_lane_keys,
    lane_of_the_day_key,
    refresh_lane_of_the_day_liveness,
    utc_day_ordinal,
)

logger = logging.getLogger(__name__)

MAINHUB_SPOTLIGHT_SCHED_PREFIX = "AOF MAINHUB — channel spotlight"

SPOTLIGHT_HEADERS: tuple[str, ...] = (
    "📺 <b>AOF NETWORK · CHANNEL OF THE DAY</b>",
    "🛍 <b>AOF WINDOW SHOP · TODAY'S LANE</b>",
    "✨ <b>AOF LINK HUB · FEATURED CHANNEL</b>",
)

# Back-compat re-exports
eligible_spotlight_lane_keys = eligible_lane_keys
spotlight_lane_for_day = lane_of_the_day_key


def spotlight_enabled() -> bool:
    raw = (os.getenv("TBCC_MAINHUB_SPOTLIGHT_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def spotlight_hour_utc() -> int:
    raw = (os.getenv("TBCC_MAINHUB_SPOTLIGHT_HOUR_UTC") or "15").strip()
    try:
        return max(0, min(23, int(raw)))
    except ValueError:
        return 15


def spotlight_album_size() -> int:
    raw = (os.getenv("TBCC_MAINHUB_SPOTLIGHT_ALBUM_SIZE") or "3").strip()
    try:
        return max(1, min(10, int(raw)))
    except ValueError:
        return 3


def _gate_href(lv: dict[str, str], key: str) -> str:
    from app.data.aof_manual_gate_links import manual_gate_url

    url = (lv.get(key) or manual_gate_url(key) or "").strip()
    if not url:
        ch = network_channel_by_key(key)
        url = (ch.invite if ch else "").strip()
    return url


def build_spotlight_caption_html(db: Session, *, network_key: str, day_ordinal: int | None = None) -> str:
    """Header + hook + lane promo_html + wrapped join CTA + stack footer."""
    import html as html_mod

    net_ch = network_channel_by_key(network_key)
    if net_ch is None:
        raise ValueError(f"unknown network_key: {network_key}")

    lv = lv_urls(db)
    day = day_ordinal if day_ordinal is not None else utc_day_ordinal()
    header = SPOTLIGHT_HEADERS[day % len(SPOTLIGHT_HEADERS)]
    hook = SPOTLIGHT_HOOKS.get(network_key, f"Today's pick: {net_ch.display_name}.")
    join_url = _gate_href(lv, network_key)
    join_line = ""
    if join_url:
        label = html_mod.escape(net_ch.display_name.strip() or network_key)
        join_line = (
            f'\n\n👉 <b>Join {label}</b> — '
            f'<a href="{html_mod.escape(join_url, quote=True)}">tap the gate</a>'
        )

    body = (net_ch.promo_html or "").strip()
    footer = build_addlist_footer(lv)
    return f"{header}\n\n<i>{html_mod.escape(hook)}</i>\n\n{body}{join_line}{footer}"


def build_spotlight_inline_keyboard(db: Session, *, network_key: str) -> list[list[dict[str, str]]]:
    from app.data.aof_network import ADDLIST_RAW, MAIN_GROUP_INVITE

    lv = lv_urls(db)
    net_ch = network_channel_by_key(network_key)
    join_url = _gate_href(lv, network_key) or (net_ch.invite if net_ch else "")
    short = (net_ch.display_name.split("·")[0].strip() if net_ch else network_key)[:32]
    row1: list[dict[str, str]] = []
    if join_url:
        row1.append({"text": f"▶ {short}", "url": join_url})
    hub = MAINHUB_RAW
    addlist = _gate_href(lv, "addlist") or ADDLIST_RAW
    loot = _gate_href(lv, "loot") or MAIN_GROUP_INVITE
    row1.append({"text": "🔗 Hub", "url": hub})
    row2 = [
        {"text": "📌 Addlist", "url": addlist},
        {"text": "🪙 Loot", "url": loot},
    ]
    return [row1, row2] if row1 else [row2]


def _spotlight_sched_name(day_key: str) -> str:
    return f"{MAINHUB_SPOTLIGHT_SCHED_PREFIX} ({day_key})"


def _already_sent_today(db: Session, day_key: str) -> bool:
    name = _spotlight_sched_name(day_key)
    row = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.name == name, ScheduledTextPost.sent_at.isnot(None))
        .first()
    )
    return row is not None


def _ensure_mainhub_channel(db: Session) -> Channel | None:
    return db.query(Channel).filter(Channel.identifier == MAINHUB_CHANNEL_IDENT).first()


def _ensure_sfw_pool(db: Session, *, album_size: int) -> ContentPool | None:
    pool = db.query(ContentPool).filter(ContentPool.name == SFW_X_PROMO_POOL_NAME).first()
    if pool:
        pool.album_size = album_size
        pool.randomize_queue = True
        return pool
    pool = ContentPool(name=SFW_X_PROMO_POOL_NAME, album_size=album_size, randomize_queue=True)
    db.add(pool)
    db.flush()
    return pool


def _upsert_spotlight_post(
    db: Session,
    *,
    channel: Channel,
    name: str,
    content: str,
    pool_id: int | None,
    album_size: int,
    buttons: list[list[dict[str, str]]] | None,
) -> ScheduledTextPost:
    now = datetime.now(timezone.utc)
    sched = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.channel_id == channel.id, ScheduledTextPost.name == name)
        .first()
    )
    if not sched:
        sched = ScheduledTextPost(
            name=name,
            channel_id=channel.id,
            content=content,
            created_at=now,
            scheduler_category="promo_bulletin",
        )
        db.add(sched)
    sched.content = content
    sched.sent_at = None
    sched.interval_minutes = None
    sched.pin_after_send = False
    sched.send_silent = False
    sched.pool_id = pool_id
    sched.album_size = album_size
    sched.pool_randomize = True
    sched.pool_only_mode = bool(pool_id)
    sched.checkout_stars_enabled = False
    sched.scheduler_category = "promo_bulletin"
    sched.buttons = json.dumps(buttons) if buttons else None
    db.flush()
    return sched


def queue_mainhub_channel_spotlight(db: Session, *, force: bool = False) -> dict[str, Any]:
    """Idempotent daily spotlight — one album post to @aofmainhub per UTC day."""
    if not spotlight_enabled() and not force:
        return {"ok": True, "skipped": True, "reason": "disabled"}

    now = datetime.now(timezone.utc)
    if not force and now.hour != spotlight_hour_utc():
        return {
            "ok": True,
            "skipped": True,
            "reason": "wrong_hour",
            "utc_hour": now.hour,
            "target_hour": spotlight_hour_utc(),
        }

    day_key = now.strftime("%Y-%m-%d")
    day_ordinal = utc_day_ordinal(now)
    if not force and _already_sent_today(db, day_key):
        return {"ok": True, "skipped": True, "reason": "already_sent", "day": day_key}

    network_key = lane_of_the_day_key(day_ordinal)
    net_ch = network_channel_by_key(network_key)
    hub = _ensure_mainhub_channel(db)
    if not hub:
        return {"ok": False, "error": "mainhub_channel_not_registered"}

    album_size = spotlight_album_size()
    pool = _ensure_sfw_pool(db, album_size=album_size)
    caption = build_spotlight_caption_html(db, network_key=network_key, day_ordinal=day_ordinal)
    buttons = build_spotlight_inline_keyboard(db, network_key=network_key)
    sched_name = _spotlight_sched_name(day_key)
    sched = _upsert_spotlight_post(
        db,
        channel=hub,
        name=sched_name,
        content=caption,
        pool_id=pool.id if pool else None,
        album_size=album_size,
        buttons=buttons,
    )
    db.commit()
    liveness_sync = refresh_lane_of_the_day_liveness(db, execute=True)
    db.commit()
    queued = queue_post_scheduler(int(sched.id), countdown=0)
    logger.info(
        "Mainhub channel spotlight queued lane=%s sched_id=%s day=%s",
        network_key,
        sched.id,
        day_key,
    )
    return {
        "ok": True,
        "day": day_key,
        "network_key": network_key,
        "display_name": net_ch.display_name if net_ch else network_key,
        "scheduler_id": sched.id,
        "pool_id": pool.id if pool else None,
        "album_size": album_size,
        "queued": queued,
        "liveness_sync": liveness_sync,
    }
