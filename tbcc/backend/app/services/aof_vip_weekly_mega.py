"""Weekly direct mega pack drop — VIP channel only."""

from __future__ import annotations

import html
import logging
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_network import AOF_VIP_IDENT
from app.models.channel import Channel
from app.models.loot import LootModifier
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.aof_growth_hub import queue_post_scheduler
from app.services.aof_vip_mirror import direct_url_for_gate
from app.services.link_gate_provider import is_gate_host
from app.services.mega_link_pipeline import resolve_to_file_host

logger = logging.getLogger(__name__)

WEEKLY_MEGA_SCHED_NAME = "AOF VIP — Weekly Mega Pack"


def vip_weekly_mega_enabled() -> bool:
    raw = (os.getenv("TBCC_VIP_WEEKLY_MEGA_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def vip_weekly_mega_day_utc() -> int:
    """0=Monday … 6=Sunday (default Friday=4)."""
    raw = (os.getenv("TBCC_VIP_WEEKLY_MEGA_DAY_UTC") or "4").strip()
    try:
        return max(0, min(6, int(raw)))
    except ValueError:
        return 4


def vip_weekly_mega_hour_utc() -> int:
    raw = (os.getenv("TBCC_VIP_WEEKLY_MEGA_HOUR_UTC") or "17").strip()
    try:
        return max(0, min(23, int(raw)))
    except ValueError:
        return 17


def _a_tag(url: str, label: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def _direct_url_for_modifier(db: Session, mod: LootModifier) -> str | None:
    from app.services.k2s_vip_access import resolve_k2s_vip_download_url

    k2s_url, _err = resolve_k2s_vip_download_url(mod)
    if k2s_url:
        return k2s_url
    target = (mod.target_url or "").strip().split()[0]
    if not target:
        return None
    if mod.bypass_vip:
        for token in (mod.source_note or "").split():
            if token.startswith("http") and not is_gate_host(token):
                return token
    if is_gate_host(target):
        direct = direct_url_for_gate(db, target)
        if direct:
            return direct
        pipeline = resolve_to_file_host(target)
        if pipeline.ok and pipeline.destination_url and not is_gate_host(pipeline.destination_url):
            return pipeline.destination_url
        return None
    return target


def pick_weekly_mega_modifier(db: Session) -> LootModifier | None:
    return (
        db.query(LootModifier)
        .filter(
            LootModifier.active.is_(True),
            LootModifier.kind == "mega_pack",
            LootModifier.target_url.isnot(None),
        )
        .order_by(LootModifier.min_rarity_tier.desc().nullslast(), LootModifier.id.desc())
        .first()
    )


def build_weekly_mega_caption_html(db: Session, mod: LootModifier, direct_url: str) -> str:
    label = html.escape((mod.label or "MEGA PACK").strip()[:80])
    tier = int(mod.min_rarity_tier or 0)
    tier_bit = f" · tier {tier}+" if tier >= 7 else ""
    return (
        f"📦 <b>VIP WEEKLY MEGA</b>{tier_bit}\n"
        f"{label}\n"
        "Direct folder — no gate in VIP. Public lane keeps the wrapped version.\n\n"
        f"{_a_tag(direct_url, 'open mega pack (direct)')}\n\n"
        "<i>Next weekly mega rotates — stay subscribed.</i>"
    )


def queue_weekly_vip_mega_drop(db: Session, *, force: bool = False) -> dict[str, Any]:
    """Idempotent weekly VIP mega post (one per ISO week unless force)."""
    if not vip_weekly_mega_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    now = datetime.now(timezone.utc)
    if not force:
        if now.weekday() != vip_weekly_mega_day_utc():
            return {"ok": True, "skipped": True, "reason": "wrong_weekday"}
        if now.hour != vip_weekly_mega_hour_utc():
            return {"ok": True, "skipped": True, "reason": "wrong_hour"}

    iso = now.isocalendar()
    week_key = f"{iso.year}-W{iso.week:02d}"
    name = f"{WEEKLY_MEGA_SCHED_NAME} ({week_key})"

    existing = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.name == name, ScheduledTextPost.sent_at.isnot(None))
        .first()
    )
    if existing and not force:
        return {"ok": True, "skipped": True, "reason": "already_sent", "week": week_key}

    mod = pick_weekly_mega_modifier(db)
    if not mod:
        return {"ok": False, "error": "no_mega_pack_modifier"}

    direct = _direct_url_for_modifier(db, mod)
    if not direct:
        return {"ok": False, "error": "no_direct_url", "modifier_id": mod.id}

    vip_ch = db.query(Channel).filter(Channel.identifier == AOF_VIP_IDENT).first()
    if not vip_ch:
        return {"ok": False, "error": "vip_channel_not_registered"}

    body = build_weekly_mega_caption_html(db, mod, direct)
    sched = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.channel_id == vip_ch.id, ScheduledTextPost.name == name)
        .first()
    )
    if not sched:
        sched = ScheduledTextPost(
            name=name,
            channel_id=vip_ch.id,
            content=body,
            send_silent=False,
            pin_after_send=False,
            created_at=now,
        )
        db.add(sched)
        db.flush()
    else:
        sched.content = body
        sched.sent_at = None
        sched.interval_minutes = None

    db.commit()
    q = queue_post_scheduler(int(sched.id), countdown=0)
    return {
        "ok": True,
        "week": week_key,
        "post_id": sched.id,
        "modifier_id": mod.id,
        "direct_url": direct,
        **q,
    }
