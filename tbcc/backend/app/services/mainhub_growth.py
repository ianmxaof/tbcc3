"""@aofmainhub CTA + pin liveness scheduler seeding."""

from __future__ import annotations

import json
from typing import Any

from app.data.aof_network import (
    MAINHUB_CHANNEL_IDENT,
    MAINHUB_SCHED_CTA_NAME,
    MAINHUB_SCHED_LIVENESS_NAME,
    SFW_X_PROMO_POOL_NAME,
)
from app.models.channel import Channel
from app.models.content_pool import ContentPool
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.aof_growth_hub import checkout_button_label_for_plan, resolve_group_access_plan_id
from app.services.aof_vip_checkout import merge_checkout_buttons
from app.services.funnel_rag import seed_default_funnel_strategies
from sqlalchemy.orm import Session

LIVENESS_CAPTIONS = [
    "🔥 Fresh drop on the network — tap the pinned VIP post for access.",
    "⚡ New lane heat — full stack in the hub pin.",
    "💎 VIP perks live — Stars · crypto · card on the pinned post.",
]

CTA_CAPTION = (
    "💳 <b>AOF VIP — 500 ⭐/30d</b> · skip the gates, daily god roll, weekly mega dump, "
    "@aofsubscriptions_bot credits. Unwrapped lanes, bigger drops, VIP-only perks — "
    "public stays on the wrapped feed. <i>Tap Pay ⭐ — instant access.</i>"
)


def _ensure_mainhub_channel(db: Session, execute: bool) -> Channel | None:
    ch = db.query(Channel).filter(Channel.identifier == MAINHUB_CHANNEL_IDENT).first()
    if ch:
        return ch
    if not execute:
        return None
    ch = Channel(
        name="AOF LINK HUB",
        identifier=MAINHUB_CHANNEL_IDENT,
        invite_link="https://telegram.me/aofmainhub",
    )
    db.add(ch)
    db.flush()
    return ch


def _ensure_sfw_pool(db: Session, execute: bool) -> ContentPool | None:
    pool = db.query(ContentPool).filter(ContentPool.name == SFW_X_PROMO_POOL_NAME).first()
    if pool:
        if execute:
            pool.album_size = 1
            pool.randomize_queue = True
        return pool
    if not execute:
        return None
    pool = ContentPool(name=SFW_X_PROMO_POOL_NAME, album_size=1, randomize_queue=True)
    db.add(pool)
    db.flush()
    return pool


def _upsert_scheduler(
    db: Session,
    *,
    ch: Channel,
    name: str,
    execute: bool,
    **fields,
) -> dict[str, Any]:
    sched = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.channel_id == ch.id, ScheduledTextPost.name == name)
        .first()
    )
    action = "update" if sched else "create"
    if execute:
        if not sched:
            sched = ScheduledTextPost(channel_id=ch.id, name=name, content=fields.get("content") or "")
            db.add(sched)
        for k, v in fields.items():
            setattr(sched, k, v)
        db.flush()
    return {"name": name, "action": action, "scheduler_id": sched.id if sched else None}


def apply_mainhub_growth(db: Session, *, execute: bool = True, post_now: bool = False) -> dict[str, Any]:
    report: dict[str, Any] = {"execute": execute, "schedulers": []}
    seed_default_funnel_strategies(db)
    ch = _ensure_mainhub_channel(db, execute)
    pool = _ensure_sfw_pool(db, execute)
    if not ch:
        report["channel"] = "missing"
        return report

    plan_id = resolve_group_access_plan_id(db)
    btn_label = checkout_button_label_for_plan(db, plan_id)
    checkout_btns = merge_checkout_buttons(
        [],
        db,
        checkout_stars_enabled=True,
        checkout_stars_plan_id=plan_id,
        checkout_button_label=btn_label,
        allow_inline_checkout=True,
    )

    report["schedulers"].append(
        _upsert_scheduler(
            db,
            ch=ch,
            name=MAINHUB_SCHED_CTA_NAME,
            execute=execute,
            content=CTA_CAPTION,
            interval_minutes=60 * 24 * 7,
            album_size=1,
            pool_id=pool.id if pool else None,
            pool_randomize=True,
            pool_only_mode=True,
            checkout_stars_enabled=True,
            checkout_stars_plan_id=plan_id,
            checkout_button_label=btn_label,
            buttons=json.dumps(checkout_btns) if checkout_btns else None,
            pin_after_send=True,
            delete_after_pin_seconds=None,
            scheduler_category="promo_bulletin",
            send_silent=False,
        )
    )

    report["schedulers"].append(
        _upsert_scheduler(
            db,
            ch=ch,
            name=MAINHUB_SCHED_LIVENESS_NAME,
            execute=execute,
            content=LIVENESS_CAPTIONS[0],
            content_variations=json.dumps(LIVENESS_CAPTIONS),
            interval_minutes=8 * 60,
            album_size=1,
            pool_id=pool.id if pool else None,
            pool_randomize=True,
            pool_only_mode=True,
            checkout_stars_enabled=False,
            pin_after_send=True,
            delete_after_pin_seconds=45,
            scheduler_category="liveness",
            send_silent=True,
        )
    )

    if post_now and execute:
        from app.workers.poster_worker import post_scheduled_text

        for row in report["schedulers"]:
            sid = row.get("scheduler_id")
            if sid:
                post_scheduled_text.delay(int(sid))
        report["queued_post_now"] = True

    return report
