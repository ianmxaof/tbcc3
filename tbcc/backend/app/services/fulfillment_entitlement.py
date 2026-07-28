"""Grant buyer_entitlements on paid fulfillment (ban-recovery ledger)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.subscription_plan import SubscriptionPlan
from app.services.entitlement_ledger import grant_entitlement

logger = logging.getLogger(__name__)


def _entitlement_kind_for_plan(plan: SubscriptionPlan) -> str:
    name = (plan.name or "").strip().lower()
    product_type = (plan.product_type or "").strip().lower()
    bot_section = (plan.bot_section or "").strip().lower()
    if "lane pass" in name:
        return "lane_pass"
    if product_type == "bundle":
        if "mega" in name:
            return "mega_pack"
        if "curated" in name or "ai pack" in name:
            return "curated_pack"
        return "bundle"
    if bot_section == "loot":
        return "loot_key"
    if bot_section == "main":
        return "vip"
    return "subscription"


def record_fulfillment_entitlement(
    db: Session,
    *,
    telegram_user_id: int,
    plan: SubscriptionPlan,
    subscription_id: int | None = None,
    invite_url: str | None = None,
    payment_method: str | None = None,
) -> dict[str, Any] | None:
    """
    Stamp entitlement ledger for every paid fulfillment.

    Never raises — fulfillment must not fail if ledger write fails.
    """
    try:
        kind = _entitlement_kind_for_plan(plan)
        name = (plan.name or "").strip().lower()
        duration_days: int | None = None
        duration_hours: int | None = None
        if kind == "lane_pass":
            duration_hours = 24
        elif kind in ("curated_pack", "mega_pack", "bundle"):
            duration_days = None
        elif (plan.duration_days or 0) > 0:
            duration_days = int(plan.duration_days)
        else:
            duration_days = 1

        note_parts = [f"plan_id={int(plan.id)}"]
        if subscription_id is not None:
            note_parts.append(f"subscription_id={int(subscription_id)}")
        if payment_method:
            note_parts.append(f"payment={payment_method}")

        row = grant_entitlement(
            db,
            telegram_user_id=int(telegram_user_id),
            kind=kind,
            plan_id=int(plan.id),
            duration_days=duration_days,
            duration_hours=duration_hours,
            invite_url=(invite_url or "").strip() or None,
            source_note="; ".join(note_parts),
        )
        db.commit()
        return {"ok": True, "entitlement_id": int(row.id), "kind": kind}
    except Exception:
        logger.exception(
            "entitlement grant failed tg=%s plan=%s",
            telegram_user_id,
            getattr(plan, "id", None),
        )
        try:
            db.rollback()
        except Exception:
            pass
        return None
