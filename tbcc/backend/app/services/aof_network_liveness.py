"""
AOF network liveness — automated perceived activity until organic traction builds.

Creates faster cadences, main-group pulse posts, drop signals on thin lanes,
pool backup posts, and milestone celebration hooks.
"""

from __future__ import annotations

import html
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.data.aof_network import (
    AOF_NETWORK_CHANNELS,
    MAIN_GROUP_IDENT,
    network_channel_by_key,
)
from app.models.channel import Channel
from app.models.content_pool import ContentPool
from app.models.media import Media
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.aof_growth_hub import (
    build_addlist_footer,
    build_checkout_caption_line,
    gate_urls,
    queue_post_scheduler,
    resolve_group_access_plan_id,
)
from app.services.growth_promo import milestone_fomo_message
from app.services.subscription_metrics import active_subscription_subscriber_count

logger = logging.getLogger(__name__)

LIVENESS_PREFIX = "AOF — network liveness"
HEARTBEAT_NAME = f"{LIVENESS_PREFIX} — heartbeat"
DROP_TICKER_NAME = f"{LIVENESS_PREFIX} — drop ticker"
SPOTLIGHT_NAME = f"{LIVENESS_PREFIX} — lane spotlight"
DROP_SIGNAL_PREFIX = f"{LIVENESS_PREFIX} — drop signal"
CELEBRATION_FIRST_SUB_NAME = "AOF — celebration — first Stars sub"
COMMANDS_PREFIX = "AOF — bot commands"

THIN_LANE_KEYS = frozenset({"goon", "bop", "abg"})
PACKS_KEY = "packs"

DEFAULT_ESTABLISHED_INTERVAL = 180
DEFAULT_THIN_INTERVAL = 120
DEFAULT_PACKS_INTERVAL = 360
DEFAULT_COMMAND_INTERVAL = 2880
DEFAULT_HEARTBEAT_INTERVAL = 240
DEFAULT_DROP_TICKER_INTERVAL = 150
DEFAULT_POOL_BACKUP_INTERVAL = 90
DEFAULT_MILESTONE_FOMO_HOURS = 6

LIVENESS_SCHEDULER_NAMES = (
    HEARTBEAT_NAME,
    DROP_TICKER_NAME,
    SPOTLIGHT_NAME,
)


def liveness_message_thread_id() -> int | None:
    """Optional fixed forum topic; ignored when TBCC_LIVENESS_RANDOM_TOPICS=1."""
    from app.services.aof_topic_mirror import liveness_random_topics_enabled

    if liveness_random_topics_enabled():
        return None
    raw = (os.getenv("TBCC_LIVENESS_MESSAGE_THREAD_ID") or "").strip()
    if not raw:
        return None
    try:
        tid = int(raw)
        return tid if tid > 0 else None
    except ValueError:
        return None


def liveness_checkout_enabled() -> bool:
    raw = (os.getenv("TBCC_LIVENESS_CHECKOUT_STARS") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _a_tag(url: str, anchor: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(anchor)}</a>'


def _env_int(key: str, default: int, *, lo: int = 15, hi: int = 10080) -> int:
    raw = (os.getenv(key) or "").strip()
    if not raw:
        return default
    try:
        return max(lo, min(hi, int(raw)))
    except ValueError:
        return default


def liveness_intervals() -> dict[str, int]:
    return {
        "established_min": _env_int("TBCC_LIVENESS_ESTABLISHED_INTERVAL_MIN", DEFAULT_ESTABLISHED_INTERVAL),
        "thin_min": _env_int("TBCC_LIVENESS_THIN_INTERVAL_MIN", DEFAULT_THIN_INTERVAL),
        "packs_min": _env_int("TBCC_LIVENESS_PACKS_INTERVAL_MIN", DEFAULT_PACKS_INTERVAL),
        "command_min": _env_int("TBCC_LIVENESS_COMMAND_INTERVAL_MIN", DEFAULT_COMMAND_INTERVAL),
        "heartbeat_min": _env_int("TBCC_LIVENESS_HEARTBEAT_INTERVAL_MIN", DEFAULT_HEARTBEAT_INTERVAL),
        "drop_ticker_min": _env_int("TBCC_LIVENESS_DROP_TICKER_INTERVAL_MIN", DEFAULT_DROP_TICKER_INTERVAL),
        "pool_backup_min": _env_int("TBCC_LIVENESS_POOL_BACKUP_INTERVAL_MIN", DEFAULT_POOL_BACKUP_INTERVAL),
        "milestone_fomo_hours": _env_int(
            "TBCC_LIVENESS_MILESTONE_FOMO_HOURS", DEFAULT_MILESTONE_FOMO_HOURS, lo=1, hi=24
        ),
    }


def _lane_interval_min(key: str, intervals: dict[str, int]) -> int | None:
    if key == PACKS_KEY:
        return intervals["packs_min"]
    if key in THIN_LANE_KEYS:
        return intervals["thin_min"]
    if key == "main":
        return None
    return intervals["established_min"]


def _approved_media_count(db: Session, pool_id: int) -> int:
    return (
        db.query(func.count(Media.id))
        .filter(Media.pool_id == pool_id, Media.status == "approved")
        .scalar()
        or 0
    )


def _build_heartbeat_variations(db: Session, lv: dict[str, str], footer: str) -> list[str]:
    from app.services.aof_main_group_copy import (
        gate_fomo_minimal_bodies,
        heartbeat_variations,
        sharpen_variations,
        vip_promo_minimal_bodies,
    )

    plan_id = resolve_group_access_plan_id(db)
    checkout = build_checkout_caption_line(plan_id)
    bodies = list(heartbeat_variations(lv, checkout))
    bodies.extend(vip_promo_minimal_bodies()[:2])
    bodies.extend(gate_fomo_minimal_bodies()[:1])
    from app.services.aof_feed_rhythm_v2 import vip_social_proof_line

    bodies.append(vip_social_proof_line(db))
    out = [b + footer for b in bodies]
    return sharpen_variations(out)


def _build_drop_ticker_variations(footer: str) -> list[str]:
    from app.services.aof_main_group_copy import drop_ticker_variations, sharpen_variations

    return sharpen_variations([b + footer for b in drop_ticker_variations()])


def _build_spotlight_variations(db: Session, lv: dict[str, str], footer: str) -> list[str]:
    from app.services.aof_main_group_copy import sharpen_variations, spotlight_variation

    checkout = build_checkout_caption_line(resolve_group_access_plan_id(db))
    out: list[str] = []
    for net_ch in AOF_NETWORK_CHANNELS:
        if net_ch.key in ("main", PACKS_KEY):
            continue
        link = lv.get(net_ch.key, net_ch.invite)
        out.append(spotlight_variation(net_ch.display_name, link, checkout) + footer)
    return sharpen_variations(out)


def _build_drop_signal_copy(net_ch, footer: str) -> list[str]:
    name = html.escape(net_ch.display_name)
    return [
        f"🚨 <b>DROP INCOMING — {name}</b>\nFresh media hits this lane next — stay in feed.{footer}",
        f"⚡ <b>{name} pulse</b>\nPipeline deposit en route from Storage Hub.{footer}",
    ]


def _upsert_recurring_scheduler(
    db: Session,
    *,
    channel_id: int,
    name: str,
    variations: list[str],
    interval_minutes: int,
    execute: bool,
    send_silent: bool = False,
    pin_after_send: bool = False,
    pool_id: int | None = None,
    message_thread_id: int | None = None,
    checkout_plan_id: int | None = None,
    checkout_button_label: str | None = None,
) -> dict[str, Any]:
    sched = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.channel_id == channel_id, ScheduledTextPost.name == name)
        .first()
    )
    entry: dict[str, Any] = {"name": name, "channel_id": channel_id, "interval_minutes": interval_minutes}
    if not variations:
        entry["status"] = "no_variations"
        return entry
    if sched:
        entry["id"] = sched.id
        entry["status"] = "exists"
    else:
        entry["status"] = "would_create"
    if execute:
        if not sched:
            sched = ScheduledTextPost(
                name=name,
                channel_id=channel_id,
                content=variations[0],
                content_variations=json.dumps(variations) if len(variations) > 1 else None,
                interval_minutes=interval_minutes,
                send_silent=send_silent,
                pin_after_send=pin_after_send,
                pool_id=pool_id,
                message_thread_id=message_thread_id,
                created_at=datetime.now(timezone.utc),
            )
            db.add(sched)
            db.flush()
            entry["id"] = sched.id
            entry["status"] = "created"
        else:
            sched.content = variations[0]
            sched.content_variations = json.dumps(variations) if len(variations) > 1 else None
            sched.interval_minutes = interval_minutes
            sched.send_silent = send_silent
            sched.pin_after_send = pin_after_send
            if pool_id is not None:
                sched.pool_id = pool_id
            if message_thread_id is not None:
                sched.message_thread_id = message_thread_id
            entry["status"] = "updated"
        if execute and checkout_plan_id and liveness_checkout_enabled():
            from app.services.aof_growth_hub import _apply_scheduler_album_checkout

            _apply_scheduler_album_checkout(
                sched,
                None,
                db,
                plan_id=int(checkout_plan_id),
                button_label=checkout_button_label or "Pay ⭐ 500",
                preserve_album_size=True,
            )
            from app.services.aof_feed_rhythm_v2 import apply_main_group_tease_media

            apply_main_group_tease_media(sched)
            entry["checkout_stars"] = True
            entry["tease_album"] = sched.album_size
        from app.services.scheduler_category import apply_scheduler_category

        apply_scheduler_category(sched)
    return entry


def apply_liveness_checkout_and_copy(
    sched: ScheduledTextPost,
    db: Session,
    *,
    plan_id: int,
    button_label: str,
    clean_footer: str,
    execute: bool,
    message_thread_id: int | None = None,
) -> dict[str, Any]:
    """Refresh footer + VIP copy + Stars checkout on an existing liveness scheduler."""
    from app.services.aof_growth_hub import (
        FOOTER_MARKER,
        _refresh_variation_footer,
        _apply_scheduler_album_checkout,
    )

    vars_ = sched.get_content_variations() or ([sched.content] if sched.content else [])
    new_vars = [_refresh_variation_footer(v, clean_footer) for v in vars_ if v]
    entry: dict[str, Any] = {
        "kind": "liveness",
        "scheduler_id": sched.id,
        "name": sched.name,
        "variations": len(new_vars),
    }
    if execute:
        if new_vars:
            sched.content = new_vars[0]
            sched.content_variations = json.dumps(new_vars) if len(new_vars) > 1 else None
        if message_thread_id is not None:
            sched.message_thread_id = message_thread_id
        if liveness_checkout_enabled():
            _apply_scheduler_album_checkout(
                sched,
                None,
                db,
                plan_id=int(plan_id),
                button_label=button_label,
                preserve_album_size=True,
            )
            from app.services.aof_feed_rhythm_v2 import apply_main_group_tease_media

            apply_main_group_tease_media(sched)
            entry["checkout_stars"] = True
            entry["tease_album"] = sched.album_size
        entry["status"] = "updated"
    else:
        entry["status"] = "would_update"
        entry["footer_marker"] = FOOTER_MARKER in (sched.content or "")
    return entry


def _tune_content_scheduler_intervals(db: Session, intervals: dict[str, int], execute: bool) -> list[dict]:
    rows: list[dict] = []
    for net_ch in AOF_NETWORK_CHANNELS:
        if net_ch.key in ("main", PACKS_KEY):
            continue
        target = _lane_interval_min(net_ch.key, intervals)
        if target is None:
            continue
        ch = db.query(Channel).filter(Channel.identifier == net_ch.identifier).first()
        if not ch:
            continue
        sched = (
            db.query(ScheduledTextPost)
            .filter(ScheduledTextPost.channel_id == ch.id, ScheduledTextPost.name == net_ch.scheduler_name)
            .first()
        )
        if not sched:
            rows.append({"key": net_ch.key, "status": "no_scheduler"})
            continue
        prev = sched.interval_minutes
        entry = {"key": net_ch.key, "scheduler_id": sched.id, "was": prev, "now": target}
        if execute:
            sched.interval_minutes = target
            entry["status"] = "updated"
        else:
            entry["status"] = "would_update"
        rows.append(entry)
    packs_ch = network_channel_by_key(PACKS_KEY)
    if packs_ch:
        ch = db.query(Channel).filter(Channel.identifier == packs_ch.identifier).first()
        if ch:
            for name in ("AOF PACKS — seed rotation", "AOF PACKS — channel promo"):
                sched = (
                    db.query(ScheduledTextPost)
                    .filter(ScheduledTextPost.channel_id == ch.id, ScheduledTextPost.name == name)
                    .first()
                )
                if sched:
                    entry = {
                        "key": PACKS_KEY,
                        "name": name,
                        "scheduler_id": sched.id,
                        "was": sched.interval_minutes,
                        "now": intervals["packs_min"],
                    }
                    if execute:
                        sched.interval_minutes = intervals["packs_min"]
                        entry["status"] = "updated"
                    else:
                        entry["status"] = "would_update"
                    rows.append(entry)
    return rows


def _tune_command_schedulers(db: Session, interval_min: int, execute: bool) -> list[dict]:
    rows: list[dict] = []
    scheds = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.name.like(f"{COMMANDS_PREFIX}%"))
        .all()
    )
    for sched in scheds:
        entry = {"id": sched.id, "name": sched.name, "was": sched.interval_minutes, "now": interval_min}
        if execute:
            sched.interval_minutes = interval_min
            sched.send_silent = True
            sched.scheduler_category = "bot_commands"
            entry["status"] = "updated"
        else:
            entry["status"] = "would_update"
        rows.append(entry)
    return rows


def _enable_pool_backup_posts(db: Session, intervals: dict[str, int], execute: bool) -> list[dict]:
    """Turn on pool interval auto-post when a lane has approved media (extra posts between scheduler runs)."""
    rows: list[dict] = []
    min_media = _env_int("TBCC_LIVENESS_POOL_BACKUP_MIN_MEDIA", 3, lo=1, hi=50)
    for net_ch in AOF_NETWORK_CHANNELS:
        if net_ch.key in ("main", PACKS_KEY):
            # PACKS: seed rotation scheduler owns captioned posts — no bare pool dumps.
            continue
        pool = db.query(ContentPool).filter(ContentPool.name == net_ch.pool_name).first()
        if not pool:
            rows.append({"key": net_ch.key, "status": "no_pool"})
            continue
        approved = _approved_media_count(db, pool.id)
        entry: dict[str, Any] = {
            "key": net_ch.key,
            "pool_id": pool.id,
            "approved_media": approved,
        }
        if approved < min_media:
            entry["status"] = "skipped_low_inventory"
            rows.append(entry)
            continue
        target_interval = intervals["pool_backup_min"]
        if net_ch.key in THIN_LANE_KEYS:
            target_interval = max(60, target_interval - 15)
        entry["interval_minutes"] = target_interval
        if execute:
            pool.auto_post_enabled = True
            pool.interval_minutes = target_interval
            from app.services.aof_feed_rhythm_v2 import network_album_size

            pool.album_size = network_album_size()
            entry["status"] = "enabled"
        else:
            entry["status"] = "would_enable"
        rows.append(entry)
    return rows


def _upsert_drop_signals(db: Session, lv: dict[str, str], intervals: dict[str, int], execute: bool) -> list[dict]:
    footer = build_addlist_footer(lv)
    rows: list[dict] = []
    signal_interval = max(intervals["thin_min"] * 2, 180)
    for key in THIN_LANE_KEYS:
        net_ch = network_channel_by_key(key)
        if not net_ch:
            continue
        ch = db.query(Channel).filter(Channel.identifier == net_ch.identifier).first()
        if not ch:
            continue
        name = f"{DROP_SIGNAL_PREFIX} — {net_ch.display_name}"
        variations = _build_drop_signal_copy(net_ch, footer)
        rows.append(
            _upsert_recurring_scheduler(
                db,
                channel_id=ch.id,
                name=name,
                variations=variations,
                interval_minutes=signal_interval,
                execute=execute,
                send_silent=True,
            )
        )
    return rows


def first_sub_celebration_sent(db: Session) -> bool:
    row = (
        db.query(ScheduledTextPost)
        .filter(
            ScheduledTextPost.name == CELEBRATION_FIRST_SUB_NAME,
            ScheduledTextPost.sent_at.isnot(None),
        )
        .first()
    )
    return row is not None


def build_first_subscription_celebration(db: Session) -> str:
    lv = gate_urls(db)
    footer = build_addlist_footer(lv)
    plan_id = resolve_group_access_plan_id(db)
    checkout = build_checkout_caption_line(plan_id)
    real = active_subscription_subscriber_count(db)
    count_line = f"{real} premium subscriber(s) and counting." if real else "The funnel just opened."
    return (
        "🎉 <b>First Stars subscription.</b> Real money, real access.\n\n"
        "Group checkout went live across the network — someone paid via ⭐. "
        f"{count_line}\n"
        f"Your turn: {checkout}{footer}"
    )


def queue_first_subscription_celebration(db: Session, *, force: bool = False) -> dict[str, Any]:
    """One-shot main-group celebration post (idempotent unless force)."""
    if not force and first_sub_celebration_sent(db):
        return {"ok": True, "skipped": True, "reason": "already_celebrated"}

    main = db.query(Channel).filter(Channel.identifier == MAIN_GROUP_IDENT).first()
    if not main:
        return {"ok": False, "error": "main_group_not_found"}

    body = build_first_subscription_celebration(db)
    sched = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.channel_id == main.id, ScheduledTextPost.name == CELEBRATION_FIRST_SUB_NAME)
        .first()
    )
    if not sched:
        sched = ScheduledTextPost(
            name=CELEBRATION_FIRST_SUB_NAME,
            channel_id=main.id,
            content=body,
            send_silent=False,
            pin_after_send=False,
            created_at=datetime.now(timezone.utc),
            scheduler_category="promo_bulletin",
        )
        db.add(sched)
        db.flush()
    else:
        sched.content = body
        sched.sent_at = None
        sched.interval_minutes = None

    db.commit()
    return {"ok": True, **queue_post_scheduler(int(sched.id), countdown=0), "post_id": sched.id}


def apply_network_liveness(db: Session, *, execute: bool = True) -> dict[str, Any]:
    """Install or refresh all liveness schedulers and cadence tuning."""
    intervals = liveness_intervals()
    lv = gate_urls(db)
    footer = build_addlist_footer(lv)
    plan_id = resolve_group_access_plan_id(db)
    from app.services.aof_growth_hub import checkout_button_label_for_plan

    button_label = checkout_button_label_for_plan(db, plan_id)
    thread_id = liveness_message_thread_id()
    main = db.query(Channel).filter(Channel.identifier == MAIN_GROUP_IDENT).first()
    pulse_rows: list[dict] = []
    if main:
        pulse_rows.append(
            _upsert_recurring_scheduler(
                db,
                channel_id=main.id,
                name=HEARTBEAT_NAME,
                variations=_build_heartbeat_variations(db, lv, footer),
                interval_minutes=intervals["heartbeat_min"],
                execute=execute,
                send_silent=True,
                message_thread_id=thread_id,
                checkout_plan_id=plan_id if liveness_checkout_enabled() else None,
                checkout_button_label=button_label,
            )
        )
        pulse_rows.append(
            _upsert_recurring_scheduler(
                db,
                channel_id=main.id,
                name=DROP_TICKER_NAME,
                variations=_build_drop_ticker_variations(footer),
                interval_minutes=intervals["drop_ticker_min"],
                execute=execute,
                send_silent=True,
                message_thread_id=thread_id,
                checkout_plan_id=plan_id if liveness_checkout_enabled() else None,
                checkout_button_label=button_label,
            )
        )
        spotlight = _build_spotlight_variations(db, lv, footer)
        pulse_rows.append(
            _upsert_recurring_scheduler(
                db,
                channel_id=main.id,
                name=SPOTLIGHT_NAME,
                variations=spotlight,
                interval_minutes=max(intervals["heartbeat_min"], intervals["drop_ticker_min"]) + 30,
                execute=execute,
                send_silent=True,
                message_thread_id=thread_id,
                checkout_plan_id=plan_id if liveness_checkout_enabled() else None,
                checkout_button_label=button_label,
            )
        )

    report = {
        "execute": execute,
        "intervals": intervals,
        "main_group_pulses": pulse_rows,
        "content_intervals": _tune_content_scheduler_intervals(db, intervals, execute),
        "command_schedulers": _tune_command_schedulers(db, intervals["command_min"], execute),
        "pool_backup": _enable_pool_backup_posts(db, intervals, execute),
        "drop_signals": _upsert_drop_signals(db, lv, intervals, execute),
        "subscriber_count_real": active_subscription_subscriber_count(db),
        "first_sub_celebrated": first_sub_celebration_sent(db),
    }
    if execute:
        db.commit()
    else:
        db.rollback()
    return report


def liveness_status(db: Session) -> dict[str, Any]:
    intervals = liveness_intervals()
    pulses: list[dict] = []
    main = db.query(Channel).filter(Channel.identifier == MAIN_GROUP_IDENT).first()
    if main:
        for name in (HEARTBEAT_NAME, DROP_TICKER_NAME, SPOTLIGHT_NAME):
            sched = (
                db.query(ScheduledTextPost)
                .filter(ScheduledTextPost.channel_id == main.id, ScheduledTextPost.name == name)
                .first()
            )
            if sched:
                pulses.append(
                    {
                        "name": name,
                        "id": sched.id,
                        "interval_minutes": sched.interval_minutes,
                        "variations": len(sched.get_content_variations() or [sched.content]),
                        "last_posted_at": sched.last_posted_at.isoformat() if sched.last_posted_at else None,
                    }
                )
            else:
                pulses.append({"name": name, "installed": False})

    command_count = (
        db.query(func.count(ScheduledTextPost.id))
        .filter(ScheduledTextPost.name.like(f"{COMMANDS_PREFIX}%"))
        .scalar()
        or 0
    )
    pool_backup_on = (
        db.query(func.count(ContentPool.id))
        .filter(
            ContentPool.name.in_([c.pool_name for c in AOF_NETWORK_CHANNELS if c.key != "main"]),
            ContentPool.auto_post_enabled.is_(True),
            ContentPool.interval_minutes > 0,
        )
        .scalar()
        or 0
    )

    return {
        "intervals": intervals,
        "main_pulses": pulses,
        "command_schedulers": command_count,
        "pools_with_backup_post": pool_backup_on,
        "subscriber_count_real": active_subscription_subscriber_count(db),
        "first_sub_celebrated": first_sub_celebration_sent(db),
    }


def post_milestone_fomo_to_main(db: Session) -> dict[str, Any]:
    """Post milestone progress line to main group (used by periodic beat task)."""
    main = db.query(Channel).filter(Channel.identifier == MAIN_GROUP_IDENT).first()
    if not main:
        return {"ok": False, "error": "main_group_not_found"}
    msg = milestone_fomo_message(db)
    footer = build_addlist_footer(gate_urls(db))
    body = f"{msg}\n\n@aofsubscriptions_bot · /subscribe · /referral{footer}"
    name = f"{LIVENESS_PREFIX} — milestone FOMO"
    sched = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.channel_id == main.id, ScheduledTextPost.name == name)
        .first()
    )
    if not sched:
        sched = ScheduledTextPost(
            name=name,
            channel_id=main.id,
            content=body,
            send_silent=True,
            pool_collective_random=True,
            pool_randomize=True,
            created_at=datetime.now(timezone.utc),
            scheduler_category="liveness",
        )
        from app.services.aof_feed_rhythm_v2 import apply_main_group_tease_media

        apply_main_group_tease_media(sched)
        db.add(sched)
        db.flush()
    else:
        sched.content = body
        from app.services.aof_feed_rhythm_v2 import apply_main_group_tease_media

        apply_main_group_tease_media(sched)
    db.commit()
    return {"ok": True, **queue_post_scheduler(int(sched.id), countdown=0)}
