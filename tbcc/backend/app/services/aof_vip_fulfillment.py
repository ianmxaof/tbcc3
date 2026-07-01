"""Post-purchase AOF VIP channel access — invite links + Telethon grant target."""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_network import (
    AOF_VIP_IDENT,
    AOF_VIP_INVITE_ONE_USE,
    AOF_VIP_INVITE_PRIMARY,
)
from app.models.channel import Channel
from app.models.subscription_plan import SubscriptionPlan
from app.services.aof_vip_perks import is_group_access_plan

logger = logging.getLogger(__name__)


def vip_primary_invite_url() -> str:
    return (os.getenv("TBCC_AOF_VIP_INVITE_URL") or AOF_VIP_INVITE_PRIMARY).strip()


def vip_one_use_invite_url() -> str:
    return (os.getenv("TBCC_AOF_VIP_INVITE_ONE_USE") or AOF_VIP_INVITE_ONE_USE).strip()


def vip_channel_ident() -> str:
    return (os.getenv("TBCC_AOF_VIP_CHANNEL_IDENT") or AOF_VIP_IDENT).strip()


def vip_channel_row(db: Session) -> Channel | None:
    ident = vip_channel_ident()
    if not ident:
        return None
    return db.query(Channel).filter(Channel.identifier == ident).first()


def fulfillment_channel_for_plan(db: Session, plan: SubscriptionPlan | None) -> Channel | None:
    """Group-access subscriptions fulfill into AOF VIP; other plans use plan.channel_id."""
    if plan and is_group_access_plan(db, int(plan.id)):
        ch = vip_channel_row(db)
        if ch:
            return ch
    if not plan or not plan.channel_id:
        return None
    return db.query(Channel).filter(Channel.id == int(plan.channel_id)).first()


def fulfillment_channel_identifier(db: Session, plan_id: int) -> str | None:
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == int(plan_id)).first()
    ch = fulfillment_channel_for_plan(db, plan)
    return str(ch.identifier) if ch and ch.identifier else None


def fulfillment_invite_link(db: Session, plan: SubscriptionPlan | None) -> str | None:
    ch = fulfillment_channel_for_plan(db, plan)
    if ch and (ch.invite_link or "").strip():
        return str(ch.invite_link).strip()
    if plan and is_group_access_plan(db, int(plan.id)):
        return vip_primary_invite_url() or None
    return None


def vip_welcome_message_html(*, invite_link: str | None = None, include_backup: bool = True) -> str:
    link = (invite_link or vip_primary_invite_url()).strip()
    bot = (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "aofsubscriptions_bot").strip().lstrip("@")
    link_line = (
        f'👉 <a href="{link}">Join AOF VIP channel</a>\n' if link else ""
    )
    backup = vip_one_use_invite_url()
    backup_line = ""
    if include_backup and backup and backup != link:
        backup_line = f'Backup link: <a href="{backup}">one-time invite</a>\n'
    body = (
        "✅ <b>AOF VIP unlocked</b>\n\n"
        f"{link_line}{backup_line}\n"
        "Your paid lane:\n"
        "• Rolled albums (3–10) · early drops · ad-free hosts\n"
        "• Daily god roll — @aof_lootgod_bot /viproll\n"
        "• Weekly mega in VIP\n"
        f"• @{bot} — companion credits + perks\n\n"
        "<i>Auto-added when possible — keep the link as backup.</i>"
    )
    return body


def wire_group_access_plan_to_vip_channel(db: Session, *, execute: bool = True) -> dict[str, Any]:
    """Point main-section subscription plan(s) at AOF VIP channel + primary invite."""
    from app.services.aof_growth_hub import resolve_group_access_plan_id

    vip = vip_channel_row(db)
    if not vip:
        return {"ok": False, "error": "vip_channel_missing", "ident": vip_channel_ident()}

    invite = vip_primary_invite_url()
    report: dict[str, Any] = {
        "ok": True,
        "vip_channel_id": vip.id,
        "vip_ident": vip.identifier,
        "invite": invite,
        "plans": [],
    }

    if execute and invite:
        if (vip.invite_link or "").strip() != invite:
            vip.invite_link = invite
            report["vip_invite_updated"] = True

    plan_ids: set[int] = set()
    pid = resolve_group_access_plan_id(db)
    plan_ids.add(int(pid))

    for plan in (
        db.query(SubscriptionPlan)
        .filter(
            SubscriptionPlan.is_active.is_(True),
            SubscriptionPlan.product_type == "subscription",
            SubscriptionPlan.bot_section == "main",
            SubscriptionPlan.price_stars > 0,
        )
        .all()
    ):
        plan_ids.add(int(plan.id))

    for plan_id in sorted(plan_ids):
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
        if not plan:
            continue
        entry: dict[str, Any] = {
            "plan_id": plan_id,
            "name": plan.name,
            "was_channel_id": plan.channel_id,
        }
        if execute:
            plan.channel_id = int(vip.id)
            entry["channel_id"] = vip.id
            entry["status"] = "updated"
        else:
            entry["would_channel_id"] = vip.id
            entry["status"] = "would_update"
        report["plans"].append(entry)

    if execute:
        db.commit()
    return report
