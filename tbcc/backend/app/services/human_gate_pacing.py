"""Human gate pacing — 'I'm not a robot' opt-in → channel invite → DM outreach list.

Strategy: offer group/channel access only after an explicit inline ack. That starts a bot DM
relationship (Telegram allows outreach to users who pressed Start / interacted). Days later,
paced FOMO DMs reuse the stars_bait outreach worker (email-list-like surface).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_network import (
    ADDLIST_RAW,
    AOF_VIP_INVITE_PRIMARY,
    MAIN_GROUP_INVITE,
    MAINHUB_RAW,
)
from app.models.funnel_dm_consent import FunnelDmConsent

logger = logging.getLogger(__name__)

GATE_TARGETS = frozenset({"loot_room", "mainhub", "addlist", "vip"})


def human_gate_enabled() -> bool:
    raw = (os.getenv("TBCC_HUMAN_GATE_ENABLED") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def dm_delay_days() -> int:
    raw = (os.getenv("TBCC_HUMAN_GATE_DM_DELAY_DAYS") or "7").strip()
    try:
        return max(0, min(90, int(raw)))
    except ValueError:
        return 7


def parse_gate_start_payload(payload: str) -> str | None:
    """Map /start deep links to gate targets. None = not a gate handoff."""
    p = (payload or "").strip().lower()
    if not p:
        return None
    if p in ("gate", "human_gate", "not_robot", "imnotarobot"):
        return "loot_room"
    if p in ("gate_loot", "gate_room", "gate_loot_room"):
        return "loot_room"
    if p in ("gate_hub", "gate_mainhub"):
        return "mainhub"
    if p == "gate_addlist":
        return "addlist"
    if p in ("gate_vip",):
        return "vip"
    return None


def resolve_gate_invite_url(target: str) -> tuple[str, str]:
    """Return (invite_url, human_label)."""
    t = (target or "loot_room").strip().lower()
    if t == "mainhub":
        return MAINHUB_RAW, "AOF Mainhub"
    if t == "addlist":
        return ADDLIST_RAW, "AOF network addlist"
    if t == "vip":
        return AOF_VIP_INVITE_PRIMARY, "AOF VIP channel"
    return MAIN_GROUP_INVITE, "Loot Room"


def gate_prompt_html(target: str) -> str:
    _url, label = resolve_gate_invite_url(target)
    return (
        f"<b>Step 1 — confirm you're human</b>\n\n"
        f"Tap <b>I'm not a robot</b> to unlock <b>{label}</b> access.\n\n"
        "This also opts you into occasional bot DMs — drops, honest deals, and VIP offers "
        "(like an email list; you can block the bot anytime).\n\n"
        "<i>No fake CAPTCHA — one tap, real invite link.</i>"
    )


def human_ack_callback_data(target: str) -> str:
    t = (target or "loot_room").strip().lower()
    if t not in GATE_TARGETS:
        t = "loot_room"
    return f"pay:human_ack:{t}"


def parse_human_ack_callback(data: str) -> str | None:
    raw = (data or "").strip()
    if not raw.startswith("pay:human_ack:"):
        return None
    target = raw.split(":", 2)[-1].strip().lower()
    return target if target in GATE_TARGETS else "loot_room"


def get_consent(db: Session, telegram_user_id: int) -> FunnelDmConsent | None:
    return (
        db.query(FunnelDmConsent)
        .filter(FunnelDmConsent.telegram_user_id == int(telegram_user_id))
        .one_or_none()
    )


def record_human_ack(
    db: Session,
    *,
    telegram_user_id: int,
    gate_target: str,
    source: str | None = None,
    username: str | None = None,
    first_name: str | None = None,
) -> FunnelDmConsent:
    target = (gate_target or "loot_room").strip().lower()
    if target not in GATE_TARGETS:
        target = "loot_room"
    invite_url, _ = resolve_gate_invite_url(target)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = get_consent(db, telegram_user_id)
    if row:
        row.gate_target = target
        row.source = (source or row.source or "")[:64] or None
        row.username = (username or row.username or "")[:64] or None
        row.first_name = (first_name or row.first_name or "")[:128] or None
        row.invite_url = invite_url
        row.dm_opt_in = True
        row.acknowledged_at = now
    else:
        row = FunnelDmConsent(
            telegram_user_id=int(telegram_user_id),
            gate_target=target,
            source=(source or "")[:64] or None,
            username=(username or "")[:64] or None,
            first_name=(first_name or "")[:128] or None,
            invite_url=invite_url,
            dm_opt_in=True,
            acknowledged_at=now,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def ack_success_html(target: str, *, already: bool = False) -> str:
    invite_url, label = resolve_gate_invite_url(target)
    prefix = "You're already verified." if already else "Verified — you're in."
    delay = dm_delay_days()
    dm_note = (
        f"Paced deal DMs may start after ~{delay} day(s)."
        if delay
        else "You may get paced deal DMs soon."
    )
    return (
        f"✅ <b>{prefix}</b>\n\n"
        f"Join <b>{label}</b>:\n{invite_url}\n\n"
        f"{dm_note}\n"
        "<i>Honest promos only — Stars / VIP / loot keys, never fake Telegram staff.</i>"
    )


def collect_human_gate_dm_user_ids(db: Session, *, limit: int = 5000) -> list[int]:
    """Users past the post-ack delay — eligible for paced outreach DMs."""
    if not human_gate_enabled():
        return []
    delay = dm_delay_days()
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=delay)
    rows = (
        db.query(FunnelDmConsent.telegram_user_id)
        .filter(
            FunnelDmConsent.dm_opt_in.is_(True),
            FunnelDmConsent.acknowledged_at <= cutoff,
        )
        .order_by(FunnelDmConsent.acknowledged_at.asc())
        .limit(max(1, min(int(limit), 20000)))
        .all()
    )
    return sorted({int(r[0]) for r in rows if r[0]})


def consent_stats(db: Session) -> dict[str, Any]:
    total = db.query(FunnelDmConsent).count()
    eligible = len(collect_human_gate_dm_user_ids(db))
    return {
        "total_consents": total,
        "dm_eligible_after_delay": eligible,
        "dm_delay_days": dm_delay_days(),
        "enabled": human_gate_enabled(),
    }
