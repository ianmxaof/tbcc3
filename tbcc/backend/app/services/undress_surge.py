"""Undress affiliate spike detection + throttled AOF surge blast (mainhub + loot room)."""

from __future__ import annotations

import html
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_network import MAIN_GROUP_IDENT, MAINHUB_CHANNEL_IDENT
from app.models.channel import Channel
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.aof_growth_hub import queue_post_scheduler
from app.services.aof_social_links import companion_bot_username, payment_bot_username
from app.services.companion_monetize_cta import loot_free_cta_url
from app.services.companion_access import affiliate_undress_url_wrapped

logger = logging.getLogger(__name__)

REDIS_EVENTS = "tbcc:undress_surge:events"
REDIS_LAST_BLAST = "tbcc:undress_surge:last_blast"
SURGE_SCHED_PREFIX = "AOF — Undress surge FOMO"


def undress_surge_enabled() -> bool:
    raw = (os.getenv("TBCC_UNDRESS_SURGE_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def undress_spike_hit_threshold() -> int:
    raw = (os.getenv("TBCC_UNDRESS_SPIKE_HITS") or "4").strip()
    try:
        return max(3, min(100, int(raw)))
    except ValueError:
        return 8


def undress_spike_window_sec() -> int:
    raw = (os.getenv("TBCC_UNDRESS_SPIKE_WINDOW_MIN") or "30").strip()
    try:
        return max(5, min(240, int(raw))) * 60
    except ValueError:
        return 30 * 60


def undress_surge_cooldown_sec() -> int:
    raw = (os.getenv("TBCC_UNDRESS_SURGE_COOLDOWN_MIN") or "180").strip()
    try:
        return max(30, min(24 * 60, int(raw))) * 60
    except ValueError:
        return 180 * 60


def _redis():
    from app.services.admin_inbox import _redis_client

    return _redis_client()


def is_undress_signal(
    *,
    source_ref: str | None = None,
    slug: str | None = None,
    link_label: str | None = None,
    url: str | None = None,
) -> bool:
    blob = " ".join(
        str(x or "")
        for x in (source_ref, slug, link_label, url)
    ).lower()
    needles = (
        "undress",
        "nodress",
        "braundress",
        "aifastedit",
        "delete_my_panties",
        "deletemypanties",
    )
    return any(n in blob for n in needles)


def record_undress_signal(kind: str) -> int:
    """Append timestamped event; return count in sliding window."""
    if not undress_surge_enabled():
        return 0
    now = time.time()
    window = undress_spike_window_sec()
    try:
        r = _redis()
        member = f"{now:.3f}:{kind}"
        r.zadd(REDIS_EVENTS, {member: now})
        r.zremrangebyscore(REDIS_EVENTS, 0, now - window)
        return int(r.zcard(REDIS_EVENTS) or 0)
    except Exception as e:
        logger.debug("undress surge record failed: %s", e)
        return 0


def spike_state() -> dict[str, Any]:
    """Current undress spike counters for briefs and dashboards."""
    now = time.time()
    window = undress_spike_window_sec()
    count = 0
    last_blast = 0.0
    try:
        r = _redis()
        r.zremrangebyscore(REDIS_EVENTS, 0, now - window)
        count = int(r.zcard(REDIS_EVENTS) or 0)
        last_blast = float(r.get(REDIS_LAST_BLAST) or 0)
    except Exception:
        pass
    threshold = undress_spike_hit_threshold()
    return {
        "enabled": undress_surge_enabled(),
        "window_min": window // 60,
        "hits_in_window": count,
        "threshold": threshold,
        "spike_active": count >= threshold,
        "last_blast_ago_min": int((now - last_blast) / 60) if last_blast else None,
        "cooldown_min": undress_surge_cooldown_sec() // 60,
    }


def on_beacon_hit_for_surge(
    *,
    source_ref: str | None,
    slug: str | None,
    link_label: str | None,
) -> dict[str, Any] | None:
    if not is_undress_signal(source_ref=source_ref, slug=slug, link_label=link_label):
        return None
    count = record_undress_signal("beacon")
    return maybe_auto_surge_from_spike(hits=count)


def on_affiliate_served_for_surge(*, source_ref: str | None, label: str | None, url: str | None) -> dict[str, Any] | None:
    if not is_undress_signal(source_ref=source_ref, link_label=label, url=url):
        return None
    count = record_undress_signal("served")
    return maybe_auto_surge_from_spike(hits=count)


def _cooldown_allows() -> bool:
    try:
        r = _redis()
        last = float(r.get(REDIS_LAST_BLAST) or 0)
        return (time.time() - last) >= undress_surge_cooldown_sec()
    except Exception:
        return True


def _mark_blast() -> None:
    try:
        r = _redis()
        r.set(REDIS_LAST_BLAST, str(time.time()))
    except Exception:
        pass


def build_surge_html(db: Session) -> str:
    loot = loot_free_cta_url()
    vip = f"https://t.me/{payment_bot_username()}?start=subscribe" if payment_bot_username() else ""
    spicy = f"https://t.me/{companion_bot_username()}" if companion_bot_username() else ""
    undress = affiliate_undress_url_wrapped(db=db)
    lines = [
        "🔥 <b>AI tools are hot right now</b>",
        "Free credits on partner bots — then bring the heat to AOF:",
    ]
    if undress:
        lines.append(f'💰 <a href="{html.escape(undress, quote=True)}">Undress credits</a>')
    if loot:
        lines.append(f'🎲 <a href="{html.escape(loot, quote=True)}">Loot God — free rolls</a>')
    if vip:
        lines.append(f'⭐ <a href="{html.escape(vip, quote=True)}">VIP — skip gates</a>')
    if spicy:
        lines.append(f'🌶 <a href="{html.escape(spicy, quote=True)}">Spicy companion</a>')
    lines.append("<i>Surge promo — limited window.</i>")
    return "\n".join(lines)


def _upsert_surge_post(db: Session, *, channel: Channel, content: str, suffix: str) -> ScheduledTextPost:
    name = f"{SURGE_SCHED_PREFIX} ({suffix})"
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
    sched.send_silent = False
    db.flush()
    return sched


def run_undress_surge_blast(db: Session, *, force: bool = False, reason: str = "spike") -> dict[str, Any]:
    """Queue one-shot surge posts to @aofmainhub + Loot Room main."""
    if not undress_surge_enabled() and not force:
        return {"ok": True, "skipped": True, "reason": "disabled"}
    if not force and not _cooldown_allows():
        return {"ok": True, "skipped": True, "reason": "cooldown"}

    state = spike_state()
    if not force and not state.get("spike_active"):
        return {"ok": True, "skipped": True, "reason": "below_threshold", **state}

    hub = db.query(Channel).filter(Channel.identifier == MAINHUB_CHANNEL_IDENT).first()
    loot = db.query(Channel).filter(Channel.identifier == MAIN_GROUP_IDENT).first()
    if not hub and not loot:
        return {"ok": False, "error": "channels_not_registered"}

    suffix = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    body = build_surge_html(db)
    queued: list[dict[str, Any]] = []

    if hub:
        sched = _upsert_surge_post(db, channel=hub, content=body, suffix=suffix)
        queued.append({**queue_post_scheduler(int(sched.id), countdown=0), "channel": "mainhub"})
    if loot:
        sched = _upsert_surge_post(db, channel=loot, content=body, suffix=suffix)
        queued.append({**queue_post_scheduler(int(sched.id), countdown=12), "channel": "loot_room"})

    db.commit()
    _mark_blast()

    try:
        from app.services.admin_inbox import push_admin_inbox_event

        push_admin_inbox_event(
            category="traffic",
            severity="important",
            title="Undress surge blast queued",
            body=(
                f"reason={reason} hits={state.get('hits_in_window')} "
                f"threshold={state.get('threshold')} targets={len(queued)}"
            ),
            meta={"code": "undress_surge_blast", "state": state, "reason": reason},
            instant=True,
        )
    except Exception:
        logger.debug("undress surge inbox notify failed", exc_info=True)

    return {"ok": True, "reason": reason, "state": state, "queued": queued}


def maybe_auto_surge_from_spike(*, hits: int) -> dict[str, Any] | None:
    if hits < undress_spike_hit_threshold():
        return None
    from app.database.session import SessionLocal

    db = SessionLocal()
    try:
        return run_undress_surge_blast(db, force=False, reason="auto_spike")
    finally:
        db.close()
