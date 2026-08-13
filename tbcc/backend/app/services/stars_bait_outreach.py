"""Paced Stars-bait DM outreach + channel cadence scheduler seeding."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import distinct
from sqlalchemy.orm import Session

from app.data.aof_network import MAIN_GROUP_IDENT
from app.models.channel import Channel
from app.models.external_payment_order import ExternalPaymentOrder
from app.models.loot import LootPlayerStats
from app.models.referral_code import ReferralCode
from app.models.scheduled_text_post import ScheduledTextPost
from app.models.subscription import Subscription
from app.services.aof_growth_hub import resolve_group_access_plan_id
from app.services.aof_vip_checkout import merge_checkout_buttons
from app.services.funnel_rag import seed_human_gate_funnel_strategies, seed_stars_bait_funnel_strategies
from app.services.stars_bait_copy import (
    StarsBaitProduct,
    bait_handoff_payload,
    checkout_start_payload,
    pick_stars_bait_variation,
    resolve_bait_plan_ids,
    stars_bait_channel_captions,
    stars_bait_inline_keyboard,
)

from app.services.human_gate_pacing import collect_human_gate_dm_user_ids

logger = logging.getLogger(__name__)

STARS_BAIT_DM_PREFIX = "AOF — stars bait DM pace"
STARS_BAIT_CHANNEL_PREFIX = "AOF — stars bait channel pace"


def stars_bait_dm_enabled() -> bool:
    raw = (os.getenv("TBCC_STARS_BAIT_DM_ENABLED") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _env_int(key: str, default: int, *, lo: int = 1, hi: int = 10080) -> int:
    raw = (os.getenv(key) or "").strip()
    if not raw:
        return default
    try:
        return max(lo, min(hi, int(raw)))
    except ValueError:
        return default


def dm_batch_size() -> int:
    return _env_int("TBCC_STARS_BAIT_DM_BATCH", 5, lo=1, hi=50)


def dm_cooldown_days() -> int:
    return _env_int("TBCC_STARS_BAIT_DM_COOLDOWN_DAYS", 7, lo=1, hi=30)


def dm_pace_interval_minutes() -> int:
    return _env_int("TBCC_STARS_BAIT_DM_INTERVAL_MIN", 45, lo=15, hi=1440)


def channel_pace_interval_minutes() -> int:
    return _env_int("TBCC_STARS_BAIT_CHANNEL_INTERVAL_MIN", 360, lo=60, hi=10080)


def _redis():
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def _dm_cooldown_key(telegram_user_id: int, product: str) -> str:
    return f"tbcc:stars_bait_dm:{int(telegram_user_id)}:{product}"


def _dm_cursor_key() -> str:
    return "tbcc:stars_bait_dm:cursor"


def _dm_unreachable_key(telegram_user_id: int) -> str:
    return f"tbcc:stars_bait_dm:unreachable:{int(telegram_user_id)}"


_DM_UNREACHABLE_TTL_SEC = 90 * 86400
_DM_UNREACHABLE_ERRORS = (
    "bot can't initiate conversation with a user",
    "chat not found",
    "user is deactivated",
    "peer_id_invalid",
)


def _mark_dm_unreachable(redis_client, telegram_user_id: int, *, reason: str) -> None:
    if not redis_client:
        return
    try:
        redis_client.setex(_dm_unreachable_key(telegram_user_id), _DM_UNREACHABLE_TTL_SEC, reason[:120])
    except Exception:
        pass


def _is_dm_unreachable(redis_client, telegram_user_id: int) -> bool:
    if not redis_client:
        return False
    try:
        return bool(redis_client.get(_dm_unreachable_key(telegram_user_id)))
    except Exception:
        return False


def collect_outreach_user_ids(db: Session, *, limit: int = 5000) -> list[int]:
    """Users who have interacted with AOF commerce (bot can DM them)."""
    ids: set[int] = set()
    for uid in collect_human_gate_dm_user_ids(db, limit=limit):
        ids.add(int(uid))
    for row in db.query(distinct(Subscription.telegram_user_id)).limit(limit).all():
        if row[0]:
            ids.add(int(row[0]))
    for row in db.query(distinct(ExternalPaymentOrder.telegram_user_id)).limit(limit).all():
        if row[0]:
            ids.add(int(row[0]))
    for row in db.query(ReferralCode.telegram_user_id).limit(limit).all():
        if row[0]:
            ids.add(int(row[0]))
    try:
        for row in db.query(distinct(LootPlayerStats.telegram_user_id)).limit(limit).all():
            if row[0]:
                ids.add(int(row[0]))
    except Exception:
        pass
    return sorted(ids)


def _product_rotation(index: int) -> StarsBaitProduct:
    products = list(StarsBaitProduct)
    return products[index % len(products)]


def send_stars_bait_dm_sync(
    db: Session,
    telegram_user_id: int,
    *,
    product: StarsBaitProduct | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Bot API DM with bait copy + single CTA button."""
    if not stars_bait_dm_enabled() and not force:
        return {"ok": True, "skipped": True, "reason": "disabled"}

    token = (os.getenv("BOT_TOKEN") or os.getenv("TBCC_PAYMENT_BOT_TOKEN") or "").strip()
    if not token:
        return {"ok": False, "error": "BOT_TOKEN_missing"}

    prod = product or _product_rotation(int(telegram_user_id) % 3)
    r = _redis()
    if r and not force and _is_dm_unreachable(r, telegram_user_id):
        return {"ok": True, "skipped": True, "reason": "unreachable", "product": prod.value}
    ck = _dm_cooldown_key(telegram_user_id, prod.value)
    if r and not force:
        try:
            if r.get(ck):
                return {"ok": True, "skipped": True, "reason": "cooldown", "product": prod.value}
        except Exception:
            pass

    variation = pick_stars_bait_variation(db, product=prod, seed=int(telegram_user_id) % 97)
    keyboard = stars_bait_inline_keyboard(variation)

    import httpx

    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": int(telegram_user_id),
                "text": variation.html,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_markup": keyboard,
            },
            timeout=30.0,
        )
        data = resp.json()
    except Exception as e:
        logger.warning("stars bait DM failed uid=%s: %s", telegram_user_id, e)
        return {"ok": False, "error": str(e)}

    if not data.get("ok"):
        err = (data.get("description") or "telegram_error").strip()
        err_l = err.lower()
        if any(marker in err_l for marker in _DM_UNREACHABLE_ERRORS):
            _mark_dm_unreachable(r, telegram_user_id, reason=err)
        return {
            "ok": False,
            "error": err,
            "product": prod.value,
            "style": variation.style.value,
        }

    if r:
        try:
            r.setex(ck, dm_cooldown_days() * 86400, "1")
        except Exception:
            pass

    return {
        "ok": True,
        "telegram_user_id": int(telegram_user_id),
        "product": prod.value,
        "style": variation.style.value,
        "button": variation.button_text,
    }


def run_stars_bait_dm_pace_tick(db: Session) -> dict[str, Any]:
    """Send next batch of paced DMs (round-robin user cursor)."""
    if not stars_bait_dm_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    users = collect_outreach_user_ids(db)
    if not users:
        return {"ok": True, "sent": 0, "reason": "no_users"}

    r = _redis()
    cursor = 0
    if r:
        try:
            cursor = int(r.get(_dm_cursor_key()) or 0)
        except Exception:
            cursor = 0

    batch = dm_batch_size()
    results: list[dict[str, Any]] = []
    sent = 0
    skipped = 0
    failed = 0
    idx = cursor % len(users)

    for _ in range(min(batch, len(users))):
        uid = users[idx]
        idx = (idx + 1) % len(users)
        out = send_stars_bait_dm_sync(db, uid)
        results.append(out)
        if out.get("skipped"):
            skipped += 1
        elif out.get("ok"):
            sent += 1
        else:
            failed += 1

    if r:
        try:
            r.set(_dm_cursor_key(), str(idx))
        except Exception:
            pass

    return {
        "ok": True,
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        "cursor": idx,
        "pool_size": len(users),
        "results": results,
    }


def apply_stars_bait_channel_pacing(db: Session, *, execute: bool = True) -> dict[str, Any]:
    """Seed main-group scheduler with bait caption rotations + checkout buttons."""
    report: dict[str, Any] = {"execute": execute, "schedulers": []}
    ch = db.query(Channel).filter(Channel.identifier == MAIN_GROUP_IDENT).first()
    if not ch:
        report["channel"] = "missing"
        return report

    captions = stars_bait_channel_captions(db)
    if not captions:
        report["error"] = "no_captions"
        return report

    plan_id = resolve_group_access_plan_id(db)
    plan_ids = resolve_bait_plan_ids(db)
    checkout_btns = merge_checkout_buttons(
        [],
        db,
        checkout_stars_enabled=True,
        checkout_stars_plan_id=plan_id,
        checkout_button_label="⭐ Full access ✅",
        allow_inline_checkout=True,
    )
    # Extra handoff rows for loot / day pass
    pay = (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "aofsubscriptions_bot").strip().lstrip("@")
    for prod in StarsBaitProduct:
        payload = bait_handoff_payload(prod)
        url = f"https://t.me/{pay}?start={payload}"
        if url not in {str(b.get("url") or "") for b in checkout_btns}:
            label = {
                StarsBaitProduct.LOOT_KEY: "🗝 Loot key",
                StarsBaitProduct.DAY_PASS: "🎫 Day pass",
                StarsBaitProduct.SUBSCRIPTION: "💎 VIP sub",
            }[prod]
            checkout_btns.append({"text": label, "url": url})

    name = STARS_BAIT_CHANNEL_PREFIX
    sched = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.channel_id == ch.id, ScheduledTextPost.name == name)
        .first()
    )
    interval = channel_pace_interval_minutes()
    entry: dict[str, Any] = {"name": name, "channel_id": ch.id, "variations": len(captions)}
    if execute:
        if not sched:
            sched = ScheduledTextPost(
                channel_id=ch.id,
                name=name,
                content=captions[0],
                created_at=datetime.now(timezone.utc),
            )
            db.add(sched)
        sched.content = captions[0]
        sched.content_variations = json.dumps(captions) if len(captions) > 1 else None
        sched.interval_minutes = interval
        sched.checkout_stars_enabled = True
        sched.checkout_stars_plan_id = plan_id
        sched.checkout_button_label = "⭐ Full access ✅"
        sched.buttons = json.dumps(checkout_btns) if checkout_btns else None
        sched.send_silent = True
        sched.pin_after_send = False
        sched.scheduler_category = "stars_bait_pace"
        db.flush()
        entry["scheduler_id"] = sched.id
        entry["status"] = "upserted"
        entry["checkout_plan_ids"] = plan_ids
    else:
        entry["status"] = "preview"
    report["schedulers"].append(entry)
    return report


def apply_stars_bait_outreach(db: Session, *, execute: bool = True, post_channel_now: bool = False) -> dict[str, Any]:
    """Seed funnel RAG + channel pacing scheduler; optional immediate channel post."""
    report: dict[str, Any] = {"execute": execute}
    try:
        report["funnel_rag_created"] = seed_stars_bait_funnel_strategies(db) if execute else 0
        report["human_gate_rag_created"] = seed_human_gate_funnel_strategies(db) if execute else 0
    except Exception as e:
        logger.warning("funnel RAG seed skipped: %s", e)
        report["funnel_rag_error"] = str(e)
    report["channel_pacing"] = apply_stars_bait_channel_pacing(db, execute=execute)
    report["dm_enabled"] = stars_bait_dm_enabled()
    report["dm_interval_min"] = dm_pace_interval_minutes()
    report["dm_batch"] = dm_batch_size()
    report["outreach_pool"] = len(collect_outreach_user_ids(db))
    try:
        from app.services.human_gate_pacing import consent_stats

        report["human_gate"] = consent_stats(db)
    except Exception:
        pass

    if post_channel_now and execute:
        sid = report.get("channel_pacing", {}).get("schedulers", [{}])[0].get("scheduler_id")
        if sid:
            from app.workers.poster_worker import post_scheduled_text

            post_scheduled_text.delay(int(sid))
            report["queued_channel_post"] = int(sid)
    return report
