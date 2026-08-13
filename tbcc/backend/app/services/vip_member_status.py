"""VIP member home copy for payment bot /status."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.services.aof_vip_weekly_mega import vip_weekly_mega_day_utc, vip_weekly_mega_hour_utc
from app.services.loot_vip_daily_pull import vip_daily_pull_available, vip_daily_pull_used_today
from app.services.subscription_access import is_aof_vip_subscriber


def _days_until_expiry(expires_at) -> int | None:
    if not expires_at:
        return None
    now = datetime.utcnow()
    exp = expires_at
    if getattr(exp, "tzinfo", None) is not None:
        exp = exp.replace(tzinfo=None)
    return max(0, (exp - now).days)


def _next_friday_mega_utc() -> datetime:
    now = datetime.now(timezone.utc)
    target_day = vip_weekly_mega_day_utc()
    target_hour = vip_weekly_mega_hour_utc()
    days_ahead = (target_day - now.weekday()) % 7
    candidate = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
    if days_ahead == 0 and now.hour >= target_hour:
        days_ahead = 7
    candidate = candidate + timedelta(days=days_ahead)
    return candidate


def build_vip_member_status_lines(
    db: Session,
    telegram_user_id: int,
    *,
    plan_name: str | None,
    expires_at,
) -> list[str]:
    uid = int(telegram_user_id)
    if not is_aof_vip_subscriber(db, uid):
        return []

    lines = ["⭐ **AOF VIP — your perks**"]
    days = _days_until_expiry(expires_at)
    plan = (plan_name or "VIP").strip()
    if days is not None:
        lines.append(f"• **{plan}** — **{days}** day(s) left")
    else:
        lines.append(f"• **{plan}** — active")

    if vip_daily_pull_available(db, uid):
        lines.append("• 🎰 **God roll:** READY — @aof_lootgod_bot `/viproll`")
    elif vip_daily_pull_used_today(db, uid):
        lines.append("• 🎰 **God roll:** claimed today — back tomorrow")
    else:
        lines.append("• 🎰 **God roll:** unavailable (check VIP status)")

    mega = _next_friday_mega_utc()
    lines.append(
        f"• 📦 **Weekly mega:** next drop {mega.strftime('%a %H:%M')} UTC (VIP direct folder)"
    )

    try:
        from app.services.companion_access import get_access

        acc = get_access(uid)
        credits = int(getattr(acc, "credits_balance", 0) or 0)
        gate = "skipped" if getattr(acc, "vip_subscriber", False) else "active"
        lines.append(f"• 🤖 **Companion:** {credits} credit(s) · gate {gate}")
    except Exception:
        pass

    lines.append("\nRenew: /subscribe · Rolls: @aof_lootgod_bot")
    return lines


def vip_member_status_for_user(
    db: Session,
    telegram_user_id: int,
    active_subs: list[dict[str, Any]],
) -> list[str] | None:
    """Return VIP home lines when user has active main-section VIP, else None."""
    uid = int(telegram_user_id)
    if not is_aof_vip_subscriber(db, uid):
        return None
    main_sub = None
    for s in active_subs:
        plan = str(s.get("plan") or "")
        if "loot" in plan.lower() and "vip" not in plan.lower():
            continue
        main_sub = s
        break
    if not main_sub and active_subs:
        main_sub = active_subs[0]
    if not main_sub:
        return build_vip_member_status_lines(db, uid, plan_name="VIP", expires_at=None)
    exp_raw = main_sub.get("expires_at")
    exp = None
    if isinstance(exp_raw, str) and exp_raw:
        try:
            exp = datetime.fromisoformat(exp_raw.replace("Z", "+00:00"))
        except ValueError:
            exp = None
    return build_vip_member_status_lines(
        db,
        uid,
        plan_name=str(main_sub.get("plan") or "VIP"),
        expires_at=exp,
    )
