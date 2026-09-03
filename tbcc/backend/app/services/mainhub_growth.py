"""@aofmainhub CTA + daily subscription / stars-bait posts + pin liveness seeding."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.data.aof_network import (
    MAINHUB_CHANNEL_IDENT,
    MAINHUB_SCHED_CTA_NAME,
    MAINHUB_SCHED_DAILY_BAIT_NAME,
    MAINHUB_SCHED_DAILY_SUB_NAME,
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
    "🔥 Fresh drop on the network — tap today's Loot Room post for access.",
    "⚡ New lane heat — Stars · crypto · card on today's hub promo.",
    "💎 Loot Room access live — Stars · crypto · card on the daily post.",
]


def _cta_caption() -> str:
    from app.data.aof_vip_membership import VIP_MEMBERSHIP_SKUS, vip_display_name

    tier = vip_display_name()
    monthly = int(VIP_MEMBERSHIP_SKUS[0].price_usd)
    return (
        f"🎫 <b>AOF {tier} — same network, five upgrades</b>\n\n"
        f"Free lanes and {tier} pull from the same pipeline. The difference is what you get at the door:\n\n"
        "📍 <b>Where</b>\n"
        "Free → scattered lanes, addlist scroll\n"
        f"{tier} → one feed, one door\n\n"
        "🎲 <b>Album size</b>\n"
        "Free → 1 (tease)\n"
        f"{tier} → 3–10 rolled per drop\n\n"
        "🔗 <b>Links</b>\n"
        "Free → gated / wrapped\n"
        f"{tier} → direct where mapped, ad-free — gate stays as fallback until every lane has a direct host\n\n"
        "⏱ <b>Timing</b>\n"
        "Free → public schedule\n"
        f"{tier} → ~60 min early\n\n"
        "🎰 <b>Daily pull</b>\n"
        "Free → loot keys / tease\n"
        f"{tier} → <code>/viproll</code> — guaranteed high-tier god roll, every day\n\n"
        "📦 <b>Weekly</b>\n"
        "Free → gated / delayed\n"
        f"{tier} → direct mega folder, Fridays, members only\n\n"
        "🤖 <b>Bonus</b> — @aof_spicybot_bot early access + bonus credits on join.\n\n"
        f"<i>Same content pipeline. {tier} is the skip button — from ${monthly}/mo.</i>\n"
        "Tap Pay ⭐, Crypto, or Card below — access starts instantly."
    )


def _daily_sub_captions() -> list[str]:
    from app.data.aof_vip_membership import VIP_INTRO_SKU, VIP_MEMBERSHIP_SKUS, vip_display_name
    from app.data.loot_lane_economy import usd_to_stars

    tier = vip_display_name()
    monthly = VIP_MEMBERSHIP_SKUS[0]
    stars = usd_to_stars(monthly.price_usd, stars_per_usd=0.012)
    intro = int(VIP_INTRO_SKU.price_usd)
    return [
        (
            f"🔑 <b>AOF {tier}</b> — <b>${int(monthly.price_usd)}</b>/mo (~{stars}⭐)\n\n"
            f"Stars in Telegram · crypto · card / USD.\n"
            f"New members: first 3 months ${intro}.\n\n"
            f"🗝 Fastest impulse: /loot — 24h Loot Room key.\n"
            f"Tap a button below — checkout opens in @aofsubscriptions_bot."
        ),
        (
            f"⭐ <b>Join the {tier}</b> today\n\n"
            f"<b>${int(monthly.price_usd)}</b>/month · {stars}⭐ · crypto · card\n"
            f"Bigger albums · earlier drops · /viproll daily.\n\n"
            f"Not ready for a month? Grab a 24h key via /loot."
        ),
        (
            f"🎫 <b>{tier} door is open</b>\n\n"
            f"One tap → Stars / crypto / card.\n"
            f"From <b>${int(monthly.price_usd)}</b>/mo. Intro ${intro} for first-timers (90d).\n\n"
            f"@aofsubscriptions_bot · /subscribe · /loot"
        ),
    ]


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


def _next_daily_fire(*, hour_utc: int, minute: int = 0) -> datetime:
    """Next occurrence of hour:minute UTC (tomorrow if that time already passed today)."""
    now = datetime.now(timezone.utc)
    target = now.replace(hour=hour_utc, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return target.replace(tzinfo=None)  # ScheduledTextPost uses naive UTC


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
        # Clear auto-pause when we deliberately reseed a live promo job.
        if fields.get("interval_minutes"):
            sched.posting_auto_paused_at = None
            sched.posting_auto_pause_reason = None
            sched.send_failure_streak = 0
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

    cta_caption = _cta_caption()
    report["schedulers"].append(
        _upsert_scheduler(
            db,
            ch=ch,
            name=MAINHUB_SCHED_CTA_NAME,
            execute=execute,
            content=cta_caption,
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

    # Daily text promos — no pool dependency so empty SFW stock can't silence the shop.
    sub_captions = _daily_sub_captions()
    report["schedulers"].append(
        _upsert_scheduler(
            db,
            ch=ch,
            name=MAINHUB_SCHED_DAILY_SUB_NAME,
            execute=execute,
            content=sub_captions[0],
            content_variations=json.dumps(sub_captions),
            interval_minutes=60 * 24,
            scheduled_at=_next_daily_fire(hour_utc=15, minute=0),  # ~08:00 PT
            album_size=None,
            pool_id=None,
            pool_only_mode=False,
            checkout_stars_enabled=True,
            checkout_stars_plan_id=plan_id,
            checkout_button_label=btn_label,
            buttons=json.dumps(checkout_btns) if checkout_btns else None,
            pin_after_send=False,
            delete_after_pin_seconds=None,
            scheduler_category="promo_bulletin",
            send_silent=False,
        )
    )

    bait_captions: list[str] = []
    try:
        from app.services.stars_bait_copy import (
            StarsBaitProduct,
            all_stars_bait_variations,
            resolve_bait_plan_ids,
        )

        plan_ids = resolve_bait_plan_ids(db)
        pay = (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "aofsubscriptions_bot").strip().lstrip("@") or (
            "aofsubscriptions_bot"
        )
        for v in all_stars_bait_variations(plan_ids):
            if v.product != StarsBaitProduct.SUBSCRIPTION:
                continue
            bait_captions.append(
                f"{v.html}\n\n"
                f'→ <a href="https://t.me/{pay}?start={v.start_payload}">{v.button_text}</a>'
            )
    except Exception as e:
        report["bait_caption_error"] = str(e)

    if bait_captions:
        bait_btns = merge_checkout_buttons(
            [],
            db,
            checkout_stars_enabled=True,
            checkout_stars_plan_id=plan_id,
            checkout_button_label="⭐ Full access ✅",
            allow_inline_checkout=True,
        )
        report["schedulers"].append(
            _upsert_scheduler(
                db,
                ch=ch,
                name=MAINHUB_SCHED_DAILY_BAIT_NAME,
                execute=execute,
                content=bait_captions[0],
                content_variations=json.dumps(bait_captions),
                interval_minutes=60 * 24,
                scheduled_at=_next_daily_fire(hour_utc=16, minute=30),  # ~09:30 PT
                album_size=None,
                pool_id=None,
                pool_only_mode=False,
                checkout_stars_enabled=True,
                checkout_stars_plan_id=plan_id,
                checkout_button_label="⭐ Full access ✅",
                buttons=json.dumps(bait_btns) if bait_btns else None,
                pin_after_send=False,
                delete_after_pin_seconds=None,
                scheduler_category="stars_bait_pace",
                send_silent=False,
            )
        )
    else:
        report["daily_bait"] = "skipped_no_captions"

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

        # Fire the two daily shop posts (+ refresh pin) immediately so the channel isn't empty until tomorrow.
        want = {MAINHUB_SCHED_DAILY_SUB_NAME, MAINHUB_SCHED_DAILY_BAIT_NAME, MAINHUB_SCHED_CTA_NAME}
        queued = []
        for row in report["schedulers"]:
            if row.get("name") in want and row.get("scheduler_id"):
                post_scheduled_text.delay(int(row["scheduler_id"]))
                queued.append(int(row["scheduler_id"]))
        report["queued_post_now"] = queued

    report["featured_plan_id"] = plan_id
    return report


# Back-compat for tests that imported the old constant.
CTA_CAPTION = _cta_caption()
