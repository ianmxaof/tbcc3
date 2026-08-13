"""AOF VIP deal-seller copy — checkout modal caption, invoice lines, urgency rotation."""

from __future__ import annotations

import html
import os
import random
from calendar import month_name
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.services.aof_growth_hub import resolve_group_access_plan_id
from app.services.growth_promo import milestone_progress_api_dict
from app.services.subscription_metrics import active_subscription_subscriber_count


def _companion_bot_username() -> str:
    return (os.getenv("TBCC_COMPANION_BOT_USERNAME") or "aof_spicybot_bot").strip().lstrip("@")


def _vip_bonus_companion_credits() -> int:
    raw = (os.getenv("TBCC_VIP_COMPANION_BONUS_CREDITS") or "3").strip()
    try:
        return max(0, min(20, int(raw)))
    except ValueError:
        return 3


def _companion_trial_photos() -> int:
    raw = (os.getenv("TBCC_COMPANION_FREE_TRIAL_PHOTOS") or "1").strip()
    try:
        return max(0, min(5, int(raw)))
    except ValueError:
        return 1


def deal_stack_bullets_html() -> list[str]:
    """Permanent value stack (HTML lines)."""
    bot = html.escape(_companion_bot_username())
    trial = _companion_trial_photos()
    bonus = _vip_bonus_companion_credits()
    companion_line = (
        f"🤖 <b>Companion early access</b> — @{bot}: "
        f"{trial} free reveal{'s' if trial != 1 else ''} + <b>{bonus} bonus credits</b> on join. "
        f"More via Stars · /referral earns credits."
    )
    return [
        "🚪 <b>Hall Pass</b> — direct hosts in VIP. Public lanes stay gated — that funds the network.",
        "🎰 <b>Daily God Roll</b> — 1 guaranteed high-tier pull/day on @aof_lootgod_bot (<code>/viproll</code>).",
        "📦 <b>Weekly Mega Pack</b> — 1 direct MEGA/TeraBox folder/week in VIP (rotating lane).",
        "⚡ <b>First Look</b> — drops hit VIP ~1h before public · bigger albums · one clean feed.",
        companion_line,
    ]


def urgency_lines_pool(db: Session | None = None) -> list[str]:
    """Rotating scarcity lines — pick one at checkout; rotate infrequently via month slot."""
    now = datetime.now(timezone.utc)
    month = month_name[now.month]
    bot = _companion_bot_username()
    lines = [
        f"🔥 <b>This week:</b> subscribe before Sunday → unlock this week's VIP mega pack retroactively.",
        f"⏳ Founding rate holds at current Stars price until the next network milestone — then it steps up.",
        f"🎰 <b>{month} perk:</b> +3 bonus god rolls on signup (limited window).",
        f"📦 Next mega drop lands Friday in VIP only — public gets the gated version later.",
        f"🚪 Hall Pass math: ~90 gate sessions/month if you're active. VIP is the skip button.",
        f"🤖 @{bot} VIP bundle: skip the gate queue + { _vip_bonus_companion_credits() } bonus photo credits on join.",
    ]
    if db is not None:
        try:
            prog = milestone_progress_api_dict(db)
            slots = prog.get("slots_to_fill")
            threshold = prog.get("next_threshold")
            if slots is not None and threshold is not None and int(slots) > 0:
                lines.append(
                    f"📊 {prog.get('current', 0)}/{threshold} subscribers — "
                    f"~{slots} spot(s) left before the next collective bonus day unlock."
                )
        except Exception:
            pass
    return lines


def pick_urgency_line(db: Session | None = None, *, seed: int | None = None) -> str:
    """One urgency line — month-stable slot so copy doesn't churn every hour."""
    pool = urgency_lines_pool(db)
    if not pool:
        return ""
    now = datetime.now(timezone.utc)
    slot = (now.year * 12 + now.month) % len(pool)
    if seed is not None:
        return pool[seed % len(pool)]
    return pool[slot]


def _build_vip_intro_deal_caption_html(bullets: list[str]) -> str:
    """First-month intro SKU — same perk stack, discounted headline."""
    from app.data.telegram_stars_howto import stars_howto_html, vip_intro_stars

    stars = vip_intro_stars()
    body_lines = [
        f"✨ <b>AOF VIP — FIRST MONTH, $10</b> · ~{stars}⭐ · one-time intro for new members only",
        "",
        "Every regular VIP perk, first month discounted. After that: standard ladder, cancel anytime.",
        "",
        "<b>What you get:</b>",
        *bullets,
        "",
        "⏳ Intro pricing is one-time, first purchase only — locks in nothing beyond month one.",
        "",
        stars_howto_html(compact=True),
        "",
        "<i>Tap Pay ⭐ or Crypto below — access starts instantly.</i>",
    ]
    return "\n".join(body_lines)


def build_vip_deal_caption_html(
    db: Session,
    plan_id: int | None = None,
    *,
    include_urgency: bool = True,
    urgency_seed: int | None = None,
    minimal: bool | None = None,
) -> str:
    """HTML caption for Pay ⭐ / Crypto checkout bot follow-up."""
    from app.models.subscription_plan import SubscriptionPlan
    from app.services.aof_main_group_copy import minimal_checkout_caption_html

    if minimal is None:
        raw = (os.getenv("TBCC_VIP_CHECKOUT_CAPTION_MINIMAL") or "0").strip().lower()
        minimal = raw not in ("0", "false", "no", "off")

    pid = int(plan_id or resolve_group_access_plan_id(db))
    if minimal:
        return minimal_checkout_caption_html(db, pid)

    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == pid).first()
    bullets = deal_stack_bullets_html()
    from app.data.aof_vip_membership import is_vip_intro_plan_name
    from app.data.telegram_stars_howto import stars_howto_html

    if plan and is_vip_intro_plan_name(str(plan.name or "")):
        return _build_vip_intro_deal_caption_html(bullets)

    stars = int(plan.price_stars or 0) if plan else 0
    days = int(plan.duration_days or 30) if plan else 30
    price_bit = f" · <b>{stars}⭐</b> / {days}d" if stars > 0 else ""

    body_lines = [
        f"🎫 <b>AOF VIP — THE HALL PASS</b>{price_bit}",
        "",
        "One tap from the paid lane. Public stays gated on purpose — VIP is your hassle-free bypass.",
        "",
        "<b>What you get:</b>",
        *bullets,
        "",
        "<b>Public vs VIP</b>",
        "Public → wrapped links · slower cadence · scattered lanes",
        "VIP → one channel · early · direct · daily roll · weekly mega · companion credits",
    ]
    if include_urgency:
        urg = pick_urgency_line(db, seed=urgency_seed)
        if urg:
            body_lines.extend(["", urg])
    body_lines.extend(["", stars_howto_html(compact=True)])
    body_lines.extend(["", "<i>Tap Pay ⭐ or Crypto below — access starts instantly.</i>"])
    return "\n".join(body_lines)


def plan_invoice_description_short(db: Session | None = None) -> str:
    """≤255 chars for Telegram Stars invoice description."""
    bot = _companion_bot_username()
    bonus = _vip_bonus_companion_credits()
    return (
        f"AOF VIP Hall Pass — 30d: direct links in VIP, daily god roll, weekly mega pack, "
        f"@{bot} early access + {bonus} credits. Public lanes stay gated."
    )[:255]


def plan_description_variations() -> list[str]:
    """Dashboard seed / description_variations_json for invoice rotation."""
    bot = _companion_bot_username()
    bonus = _vip_bonus_companion_credits()
    return [
        plan_invoice_description_short(),
        f"Hall Pass: skip gates in VIP · daily /viproll god roll · weekly direct mega · @{bot} + {bonus} credits.",
        "VIP silo: early drops, unwrapped links, bigger albums — plus companion early access & bonus photo credits.",
        "Public = gated lanes. VIP = bypass + recurring perks. One tap Stars or crypto checkout.",
    ]


def sync_plan_deal_descriptions(db: Session, plan_id: int | None = None) -> dict[str, Any]:
    """Write deal copy onto the group-access plan (idempotent content refresh)."""
    import json

    from app.models.subscription_plan import SubscriptionPlan

    pid = int(plan_id or resolve_group_access_plan_id(db))
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == pid).first()
    if not plan:
        return {"ok": False, "error": "plan_not_found", "plan_id": pid}
    plan.description = plan_invoice_description_short(db)
    plan.description_variations_json = json.dumps(plan_description_variations())
    db.commit()
    return {"ok": True, "plan_id": pid, "description_len": len(plan.description or "")}
