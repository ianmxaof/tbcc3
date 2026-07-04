"""Drop countdown ticker — edit-in-place reminders before lane drops."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.data.aof_network import MAIN_GROUP_IDENT, network_channel_by_key
from app.models.channel import Channel
from app.models.content_pool import ContentPool
from app.models.drop_countdown import DropCountdownSession
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.aof_growth_hub import build_addlist_footer, gate_urls, queue_post_scheduler

logger = logging.getLogger(__name__)

COUNTDOWN_TICKS_MINUTES = (60, 45, 30, 15, 5, 4, 3, 2, 1)
REDIS_COUNTDOWN_KEY = "tbcc:drop_countdown:active_msg"


def drop_countdown_enabled() -> bool:
    return (os.getenv("TBCC_DROP_COUNTDOWN_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _bot_token() -> str:
    return (os.getenv("BOT_TOKEN") or os.getenv("TBCC_PAYMENT_BOT_TOKEN") or "").strip()


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _countdown_redis_key(chat_id: str, thread_id: int | None) -> str:
    tid = int(thread_id or 0)
    return f"{REDIS_COUNTDOWN_KEY}:{chat_id}:{tid}"


def _lane_display(lane_key: str) -> str:
    ch = network_channel_by_key(lane_key)
    return ch.display_name if ch else lane_key.upper()


def build_countdown_html(session: DropCountdownSession, *, label: str) -> str:
    lane = _lane_display(session.lane_key)
    drop_at = session.drop_at.replace(tzinfo=timezone.utc) if session.drop_at else None
    eta = drop_at.strftime("%H:%M UTC") if drop_at else ""
    return (
        f"⏳ <b>DROP IN {label}</b> — {lane}\n"
        f"Pipeline deposit hits the lane feed{' @ ' + eta if eta else ''}.\n"
        "<i>Stay in feed — VIP gets early mirror.</i>"
    )


def _tg_post(method: str, payload: dict) -> dict[str, Any]:
    token = _bot_token()
    if not token:
        return {"ok": False, "error": "BOT_TOKEN unset"}
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        with httpx.Client(timeout=20) as client:
            r = client.post(url, json=payload)
            data = r.json() if r.content else {}
            if r.status_code != 200 or not data.get("ok"):
                return {"ok": False, "error": str(data)[:400], "status": r.status_code}
            return {"ok": True, "result": data.get("result")}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def send_or_edit_countdown(
    db: Session,
    session: DropCountdownSession,
    *,
    label: str,
) -> dict[str, Any]:
    """One visible countdown slot — edit previous message or send new."""
    if not drop_countdown_enabled():
        return {"ok": False, "skipped": True}

    chat_id = session.countdown_chat_id or session.channel_identifier
    text = build_countdown_html(session, label=label)
    thread_id = session.message_thread_id
    rkey = _countdown_redis_key(str(chat_id), thread_id)
    msg_id = session.countdown_message_id

    try:
        r = _redis()
        cached = r.get(rkey)
        if cached and not msg_id:
            try:
                msg_id = int(json.loads(cached).get("message_id") or 0) or None
            except (json.JSONDecodeError, TypeError, ValueError):
                msg_id = None
    except Exception:
        pass

    if msg_id:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": int(msg_id),
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        out = _tg_post("editMessageText", payload)
        if out.get("ok"):
            session.last_tick_label = label
            session.updated_at = datetime.utcnow()
            db.flush()
            return out
        logger.info("drop countdown edit failed, re-sending: %s", out.get("error"))

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": True,
    }
    if thread_id:
        payload["message_thread_id"] = int(thread_id)
    out = _tg_post("sendMessage", payload)
    if not out.get("ok"):
        session.status = "failed"
        session.error_note = str(out.get("error") or "send failed")[:500]
        db.flush()
        return out

    result = out.get("result") or {}
    new_id = result.get("message_id")
    session.countdown_message_id = int(new_id) if new_id else None
    session.countdown_chat_id = str(chat_id)
    session.last_tick_label = label
    session.status = "countdown"
    session.updated_at = datetime.utcnow()
    db.flush()

    try:
        r = _redis()
        r.set(
            rkey,
            json.dumps({"message_id": session.countdown_message_id, "session_id": session.id}),
            ex=86400,
        )
    except Exception:
        pass
    return out


def delete_countdown_message(session: DropCountdownSession) -> None:
    if not session.countdown_message_id or not session.countdown_chat_id:
        return
    _tg_post(
        "deleteMessage",
        {
            "chat_id": session.countdown_chat_id,
            "message_id": int(session.countdown_message_id),
        },
    )
    try:
        r = _redis()
        r.delete(_countdown_redis_key(str(session.countdown_chat_id), session.message_thread_id))
    except Exception:
        pass


def schedule_drop_countdown(
    db: Session,
    *,
    lane_key: str,
    drop_at: datetime,
    channel_identifier: str | None = None,
    message_thread_id: int | None = None,
    pool_id: int | None = None,
    execute: bool = True,
) -> dict[str, Any]:
    """Create drop session and queue Celery ETA ticks."""
    if drop_at.tzinfo is None:
        drop_at = drop_at.replace(tzinfo=timezone.utc)
    else:
        drop_at = drop_at.astimezone(timezone.utc)

    ident = (channel_identifier or MAIN_GROUP_IDENT).strip()
    ch = db.query(Channel).filter(Channel.identifier == ident).first()
    if not ch:
        return {"ok": False, "error": "channel_not_found", "identifier": ident}

    net_ch = network_channel_by_key(lane_key)
    if pool_id is None and net_ch:
        pool = db.query(ContentPool).filter(ContentPool.name == net_ch.pool_name).first()
        pool_id = pool.id if pool else None

    if not execute:
        return {
            "ok": True,
            "preview": True,
            "lane_key": lane_key,
            "drop_at": drop_at.isoformat(),
            "channel_id": ch.id,
            "pool_id": pool_id,
        }

    session = DropCountdownSession(
        channel_id=ch.id,
        channel_identifier=ident,
        message_thread_id=message_thread_id,
        lane_key=lane_key.strip().lower(),
        pool_id=pool_id,
        drop_at=drop_at.replace(tzinfo=None),
        status="scheduled",
        created_at=datetime.utcnow(),
    )
    db.add(session)
    db.flush()

    from app.workers.drop_countdown_worker import enqueue_drop_countdown_chain

    enqueue_drop_countdown_chain(int(session.id), drop_at=drop_at)
    db.commit()
    return {"ok": True, "session_id": session.id, "drop_at": drop_at.isoformat(), "lane_key": lane_key}


def tick_drop_countdown(db: Session, session_id: int, *, minutes_left: int | None = None) -> dict[str, Any]:
    session = db.query(DropCountdownSession).filter(DropCountdownSession.id == int(session_id)).first()
    if not session or session.status in ("dropped", "cancelled", "failed"):
        return {"ok": True, "skipped": True, "reason": "inactive"}

    if minutes_left is not None and minutes_left > 0:
        label = f"{minutes_left}m" if minutes_left >= 5 else str(minutes_left)
        out = send_or_edit_countdown(db, session, label=label)
        db.commit()
        return out

    return execute_lane_drop(db, session)


def execute_lane_drop(db: Session, session: DropCountdownSession) -> dict[str, Any]:
    """Delete ticker and fire pool drop post."""
    delete_countdown_message(session)

    net_ch = network_channel_by_key(session.lane_key)
    ch = db.query(Channel).filter(Channel.id == session.channel_id).first()
    if not ch or not net_ch:
        session.status = "failed"
        session.error_note = "lane_or_channel_missing"
        db.commit()
        return {"ok": False, "error": session.error_note}

    lv = gate_urls(db)
    footer = build_addlist_footer(lv)
    from app.services.aof_vip_promo_copy import vip_promo_with_lane

    body = (
        f"🚨 <b>DROP LIVE — {_lane_display(session.lane_key)}</b>\n"
        f"{vip_promo_with_lane(_lane_display(session.lane_key))}"
        f"{footer}"
    )

    sched = ScheduledTextPost(
        name=f"AOF — drop live — {net_ch.display_name}",
        channel_id=ch.id,
        content=body,
        pool_id=session.pool_id,
        album_size=3,
        pool_randomize=True,
        send_silent=False,
        message_thread_id=session.message_thread_id,
        created_at=datetime.utcnow(),
    )
    from app.services.aof_growth_hub import (
        _apply_scheduler_album_checkout,
        checkout_button_label_for_plan,
        resolve_group_access_plan_id,
    )

    plan_id = resolve_group_access_plan_id(db)
    pool = db.query(ContentPool).filter(ContentPool.id == session.pool_id).first() if session.pool_id else None
    _apply_scheduler_album_checkout(
        sched,
        pool,
        db,
        plan_id=plan_id,
        button_label=checkout_button_label_for_plan(db, plan_id),
        preserve_album_size=False,
    )
    sched.album_size = 3
    db.add(sched)
    db.flush()
    session.scheduled_post_id = sched.id
    session.status = "dropped"
    session.updated_at = datetime.utcnow()
    db.commit()

    queued = queue_post_scheduler(int(sched.id), countdown=0)
    return {"ok": True, "session_id": session.id, "post_id": sched.id, **queued}


def upcoming_ticks(drop_at: datetime) -> list[tuple[int, datetime]]:
    """Return (minutes_left, eta_utc) for each countdown tick."""
    if drop_at.tzinfo is None:
        drop_at = drop_at.replace(tzinfo=timezone.utc)
    out: list[tuple[int, datetime]] = []
    now = datetime.now(timezone.utc)
    for m in COUNTDOWN_TICKS_MINUTES:
        eta = drop_at - timedelta(minutes=m)
        if eta > now:
            out.append((m, eta))
    if drop_at > now:
        out.append((0, drop_at))
    return out
