"""Queue weekly build-log posts — Loot Room PATCH NOTES + @aofmainhub synopsis."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.data.aof_network import (
    LOOT_ROOM_PATCH_NOTES_SCHED_PREFIX,
    MAIN_GROUP_IDENT,
    MAIN_GROUP_PATCH_NOTES_TOPIC_ID,
    MAINHUB_CHANNEL_IDENT,
    MAINHUB_WEEKLY_BUILD_LOG_SCHED_PREFIX,
)
from app.models.channel import Channel
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.aof_growth_hub import queue_post_scheduler
from app.services.build_log_draft import (
    collect_weekly_build_log_context,
    draft_mainhub_snippet_html,
    draft_patch_notes_html,
    extract_build_log_items,
    mainhub_patch_notes_buttons,
)

logger = logging.getLogger(__name__)


def weekly_build_log_enabled() -> bool:
    raw = (os.getenv("TBCC_WEEKLY_BUILD_LOG_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def weekly_build_log_day_utc() -> int:
    """0=Monday … 6=Sunday (legacy UTC gate — prefer local TZ helpers)."""
    raw = (os.getenv("TBCC_WEEKLY_BUILD_LOG_DAY_UTC") or "0").strip()
    try:
        return max(0, min(6, int(raw)))
    except ValueError:
        return 0


def weekly_build_log_timezone() -> ZoneInfo:
    tz = (os.getenv("TBCC_WEEKLY_BUILD_LOG_TZ") or "America/Los_Angeles").strip()
    try:
        return ZoneInfo(tz)
    except Exception:
        return ZoneInfo("America/Los_Angeles")


def weekly_build_log_local_weekday() -> int:
    """0=Monday … 6=Sunday."""
    raw = (os.getenv("TBCC_WEEKLY_BUILD_LOG_WEEKDAY") or os.getenv("TBCC_WEEKLY_BUILD_LOG_DAY_UTC") or "0").strip()
    try:
        return max(0, min(6, int(raw)))
    except ValueError:
        return 0


def weekly_build_log_local_hour() -> int:
    raw = (os.getenv("TBCC_WEEKLY_BUILD_LOG_LOCAL_HOUR") or "9").strip()
    try:
        return max(0, min(23, int(raw)))
    except ValueError:
        return 9


def weekly_build_log_local_minute() -> int:
    raw = (os.getenv("TBCC_WEEKLY_BUILD_LOG_LOCAL_MINUTE") or "30").strip()
    try:
        return max(0, min(59, int(raw)))
    except ValueError:
        return 30


def is_weekly_build_log_due(now_utc: datetime | None = None) -> bool:
    """True when local wall clock matches configured Monday 09:30 (default San Jose / LA)."""
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(weekly_build_log_timezone())
    return (
        local.weekday() == weekly_build_log_local_weekday()
        and local.hour == weekly_build_log_local_hour()
        and local.minute == weekly_build_log_local_minute()
    )


def weekly_build_log_hour_utc() -> int:
    raw = (os.getenv("TBCC_WEEKLY_BUILD_LOG_HOUR_UTC") or "16").strip()
    try:
        return max(0, min(23, int(raw)))
    except ValueError:
        return 16


def weekly_build_log_top_k() -> int:
    raw = (os.getenv("TBCC_WEEKLY_BUILD_LOG_TOP_K") or "8").strip()
    try:
        return max(3, min(12, int(raw)))
    except ValueError:
        return 8


def weekly_build_log_snippet_top_k() -> int:
    raw = (os.getenv("TBCC_WEEKLY_BUILD_LOG_SNIPPET_TOP_K") or "4").strip()
    try:
        return max(2, min(6, int(raw)))
    except ValueError:
        return 4


def _iso_week_key(now: datetime) -> str:
    iso = now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _already_sent(db: Session, name: str) -> bool:
    row = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.name == name, ScheduledTextPost.sent_at.isnot(None))
        .first()
    )
    return row is not None


def _upsert_one_shot_post(
    db: Session,
    *,
    channel: Channel,
    name: str,
    content: str,
    message_thread_id: int | None = None,
    buttons: list | None = None,
    scheduler_category: str = "promo_bulletin",
    pin_after_send: bool = False,
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
        )
        db.add(sched)
    sched.content = content
    sched.message_thread_id = message_thread_id
    sched.sent_at = None
    sched.interval_minutes = None
    sched.pin_after_send = pin_after_send
    sched.send_silent = False
    sched.scheduler_category = scheduler_category
    if buttons:
        sched.buttons = json.dumps(buttons)
    else:
        sched.buttons = None
    db.flush()
    return sched


def queue_weekly_build_log_posts(db: Session, *, force: bool = False) -> dict[str, Any]:
    """
    Idempotent weekly pair:
    1. Full patch notes → Loot Room PATCH NOTES topic (2408)
    2. Synopsis → @aofmainhub (with button to topic)
    """
    if not weekly_build_log_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    now = datetime.now(timezone.utc)
    if not force:
        use_local = (os.getenv("TBCC_WEEKLY_BUILD_LOG_USE_LOCAL_TZ") or "1").strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
        if use_local:
            if not is_weekly_build_log_due(now):
                return {"ok": True, "skipped": True, "reason": "wrong_local_time"}
        else:
            if now.weekday() != weekly_build_log_day_utc():
                return {"ok": True, "skipped": True, "reason": "wrong_weekday"}
            if now.hour != weekly_build_log_hour_utc():
                return {"ok": True, "skipped": True, "reason": "wrong_hour"}

    week_key = _iso_week_key(now)
    patch_name = f"{LOOT_ROOM_PATCH_NOTES_SCHED_PREFIX} ({week_key})"
    hub_name = f"{MAINHUB_WEEKLY_BUILD_LOG_SCHED_PREFIX} ({week_key})"

    if not force and _already_sent(db, patch_name):
        return {"ok": True, "skipped": True, "reason": "already_sent", "week": week_key}

    ctx = collect_weekly_build_log_context()
    items = extract_build_log_items(ctx, top_k=weekly_build_log_top_k())
    if not items and not force:
        return {"ok": True, "skipped": True, "reason": "no_content", "week": week_key}

    loot_ch = db.query(Channel).filter(Channel.identifier == MAIN_GROUP_IDENT).first()
    hub_ch = db.query(Channel).filter(Channel.identifier == MAINHUB_CHANNEL_IDENT).first()
    if not loot_ch:
        return {"ok": False, "error": "loot_room_channel_not_registered"}
    if not hub_ch:
        return {"ok": False, "error": "mainhub_channel_not_registered"}

    patch_body = draft_patch_notes_html(
        items,
        week_key=week_key,
        commit_count=ctx.commit_count,
        since_label=ctx.since_label,
    )
    snippet_body = draft_mainhub_snippet_html(
        items,
        week_key=week_key,
        top_k=weekly_build_log_snippet_top_k(),
    )
    buttons = mainhub_patch_notes_buttons()

    patch_sched = _upsert_one_shot_post(
        db,
        channel=loot_ch,
        name=patch_name,
        content=patch_body,
        message_thread_id=MAIN_GROUP_PATCH_NOTES_TOPIC_ID,
        scheduler_category="promo_bulletin",
        pin_after_send=False,
    )
    hub_sched = _upsert_one_shot_post(
        db,
        channel=hub_ch,
        name=hub_name,
        content=snippet_body,
        buttons=buttons,
        scheduler_category="promo_bulletin",
        pin_after_send=False,
    )
    db.commit()

    patch_q = queue_post_scheduler(int(patch_sched.id), countdown=0)
    hub_q = queue_post_scheduler(int(hub_sched.id), countdown=12)

    report = {
        "ok": True,
        "week": week_key,
        "commit_count": ctx.commit_count,
        "highlight_count": len(items),
        "patch_post_id": patch_sched.id,
        "mainhub_post_id": hub_sched.id,
        "patch_queue": patch_q,
        "mainhub_queue": hub_q,
    }
    logger.info("weekly build log queued: %s", report)
    return report
