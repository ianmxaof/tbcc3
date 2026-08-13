"""Lifecycle DM outreach — subscription renewal, loot + companion re-engagement."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models.loot import LootPlayerStats
from app.models.subscription import Subscription
from app.services.lifecycle_dm_copy import (
    CompanionReengageSegment,
    LootReengageSegment,
    LOOT_INACTIVE_DAYS,
    COMPANION_INACTIVE_DAYS,
    SUBSCRIPTION_SEGMENT_OFFSETS,
    SubscriptionLifecycleSegment,
    build_companion_reengage_message,
    build_loot_reengage_message,
    build_subscription_lifecycle_message,
    lifecycle_inline_keyboard,
)
from app.services.companion_access import companion_had_real_session, list_companion_user_ids_active_on_date
from app.services.stars_bait_outreach import _is_dm_unreachable, _mark_dm_unreachable

logger = logging.getLogger(__name__)

_SENT_PREFIX = "tbcc:lifecycle_dm:sent:"
_SENT_TTL_SEC = 400 * 86400


def lifecycle_dm_enabled() -> bool:
    raw = (os.getenv("TBCC_LIFECYCLE_DM_ENABLED") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def subscription_lifecycle_enabled() -> bool:
    raw = (os.getenv("TBCC_LIFECYCLE_DM_SUB_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def loot_reengage_enabled() -> bool:
    raw = (os.getenv("TBCC_LIFECYCLE_DM_LOOT_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def companion_reengage_enabled() -> bool:
    raw = (os.getenv("TBCC_LIFECYCLE_DM_COMPANION_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _env_int(key: str, default: int, *, lo: int = 1, hi: int = 500) -> int:
    raw = (os.getenv(key) or "").strip()
    if not raw:
        return default
    try:
        return max(lo, min(hi, int(raw)))
    except ValueError:
        return default


def dm_batch_size() -> int:
    return _env_int("TBCC_LIFECYCLE_DM_BATCH", 100, lo=1, hi=500)


def _redis():
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def _utc_today() -> date:
    return datetime.utcnow().date()


def _sent_key(*, segment: str, entity_id: int) -> str:
    return f"{_SENT_PREFIX}{segment}:{int(entity_id)}"


def _already_sent(redis_client, *, segment: str, entity_id: int) -> bool:
    if not redis_client:
        return False
    try:
        return bool(redis_client.get(_sent_key(segment=segment, entity_id=entity_id)))
    except Exception:
        return False


def _mark_sent(redis_client, *, segment: str, entity_id: int) -> None:
    if not redis_client:
        return
    try:
        redis_client.setex(_sent_key(segment=segment, entity_id=entity_id), _SENT_TTL_SEC, "1")
    except Exception:
        pass


def _payment_bot_token() -> str:
    return (os.getenv("BOT_TOKEN") or os.getenv("TBCC_PAYMENT_BOT_TOKEN") or "").strip()


def _loot_bot_token(db: Session) -> str:
    from app.services.loot_bot_settings_effective import resolve_bot_token_raw

    return (resolve_bot_token_raw(db) or os.getenv("TBCC_LOOT_BOT_TOKEN") or "").strip()


def _companion_bot_token() -> str:
    return (os.getenv("TBCC_COMPANION_BOT_TOKEN") or "").strip()


@dataclass(frozen=True)
class LifecycleDmCandidate:
    kind: str  # subscription | loot | companion
    segment: str
    telegram_user_id: int
    entity_id: int
    plan_name: str | None = None
    expires_at: datetime | None = None
    plan_id: int | None = None


def _subscription_candidates_for_segment(
    db: Session,
    segment: SubscriptionLifecycleSegment,
) -> list[LifecycleDmCandidate]:
    offset = SUBSCRIPTION_SEGMENT_OFFSETS[segment]
    target = _utc_today() + timedelta(days=offset)
    is_pre = offset >= 0
    status = "active" if is_pre else "expired"

    rows = (
        db.query(Subscription)
        .filter(
            Subscription.status == status,
            Subscription.expires_at.isnot(None),
        )
        .all()
    )
    out: list[LifecycleDmCandidate] = []
    for sub in rows:
        exp = sub.expires_at
        if not exp:
            continue
        exp_date = exp.date() if hasattr(exp, "date") else exp
        if exp_date != target:
            continue
        out.append(
            LifecycleDmCandidate(
                kind="subscription",
                segment=segment.value,
                telegram_user_id=int(sub.telegram_user_id),
                entity_id=int(sub.id),
                plan_name=sub.plan,
                expires_at=exp,
                plan_id=int(sub.plan_id) if sub.plan_id else None,
            )
        )
    return out


def collect_subscription_candidates(db: Session) -> list[LifecycleDmCandidate]:
    if not subscription_lifecycle_enabled():
        return []
    out: list[LifecycleDmCandidate] = []
    for segment in SubscriptionLifecycleSegment:
        out.extend(_subscription_candidates_for_segment(db, segment))
    return out


def _loot_candidates_for_segment(db: Session, segment: LootReengageSegment) -> list[LifecycleDmCandidate]:
    inactive_days = LOOT_INACTIVE_DAYS[segment]
    target_date = _utc_today() - timedelta(days=inactive_days)
    rows = (
        db.query(LootPlayerStats)
        .filter(
            LootPlayerStats.roll_count > 0,
            LootPlayerStats.last_roll_at.isnot(None),
        )
        .all()
    )
    out: list[LifecycleDmCandidate] = []
    for row in rows:
        last = row.last_roll_at
        if not last:
            continue
        last_date = last.date() if hasattr(last, "date") else last
        if last_date != target_date:
            continue
        out.append(
            LifecycleDmCandidate(
                kind="loot",
                segment=segment.value,
                telegram_user_id=int(row.telegram_user_id),
                entity_id=int(row.telegram_user_id),
            )
        )
    return out


def collect_loot_candidates(db: Session) -> list[LifecycleDmCandidate]:
    if not loot_reengage_enabled():
        return []
    out: list[LifecycleDmCandidate] = []
    for segment in LootReengageSegment:
        out.extend(_loot_candidates_for_segment(db, segment))
    return out


def _companion_candidates_for_segment(segment: CompanionReengageSegment) -> list[LifecycleDmCandidate]:
    inactive_days = COMPANION_INACTIVE_DAYS[segment]
    target_date = _utc_today() - timedelta(days=inactive_days)
    out: list[LifecycleDmCandidate] = []
    for uid in list_companion_user_ids_active_on_date(target_date):
        if not companion_had_real_session(uid):
            continue
        out.append(
            LifecycleDmCandidate(
                kind="companion",
                segment=segment.value,
                telegram_user_id=int(uid),
                entity_id=int(uid),
            )
        )
    return out


def collect_companion_candidates(db: Session) -> list[LifecycleDmCandidate]:
    if not companion_reengage_enabled():
        return []
    out: list[LifecycleDmCandidate] = []
    for segment in CompanionReengageSegment:
        out.extend(_companion_candidates_for_segment(segment))
    return out


def collect_lifecycle_candidates(db: Session) -> list[LifecycleDmCandidate]:
    """Subscription reminders first, then companion flirt DMs, then loot."""
    subs = collect_subscription_candidates(db)
    companion = collect_companion_candidates(db)
    loot = collect_loot_candidates(db)
    return _dedupe_by_user(subs + companion + loot)


def _dedupe_by_user(candidates: list[LifecycleDmCandidate]) -> list[LifecycleDmCandidate]:
    """At most one lifecycle DM per user per daily tick (highest-priority segment wins)."""
    seen: set[int] = set()
    out: list[LifecycleDmCandidate] = []
    for candidate in candidates:
        uid = int(candidate.telegram_user_id)
        if uid in seen:
            continue
        seen.add(uid)
        out.append(candidate)
    return out


def send_lifecycle_dm_sync(
    db: Session,
    candidate: LifecycleDmCandidate,
    *,
    force: bool = False,
) -> dict[str, Any]:
    if not lifecycle_dm_enabled() and not force:
        return {"ok": True, "skipped": True, "reason": "disabled"}

    r = _redis()
    if r and not force and _already_sent(r, segment=candidate.segment, entity_id=candidate.entity_id):
        return {"ok": True, "skipped": True, "reason": "already_sent", "segment": candidate.segment}

    if r and not force and _is_dm_unreachable(r, candidate.telegram_user_id):
        return {"ok": True, "skipped": True, "reason": "unreachable", "segment": candidate.segment}

    if candidate.kind == "subscription":
        seg = SubscriptionLifecycleSegment(candidate.segment)
        plan_id = candidate.plan_id
        if not plan_id:
            from app.services.aof_growth_hub import resolve_group_access_plan_id

            plan_id = resolve_group_access_plan_id(db)
        msg = build_subscription_lifecycle_message(
            seg,
            plan_name=candidate.plan_name,
            expires_at=candidate.expires_at,
            plan_id=plan_id,
        )
        token = _payment_bot_token()
    elif candidate.kind == "companion":
        seg = CompanionReengageSegment(candidate.segment)
        msg = build_companion_reengage_message(seg, telegram_user_id=candidate.telegram_user_id)
        token = _companion_bot_token()
    else:
        seg = LootReengageSegment(candidate.segment)
        msg = build_loot_reengage_message(seg)
        token = _loot_bot_token(db)

    if not token:
        return {"ok": False, "error": "bot_token_missing", "kind": candidate.kind}

    keyboard = lifecycle_inline_keyboard(msg)
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": int(candidate.telegram_user_id),
                "text": msg.html,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_markup": keyboard,
            },
            timeout=30.0,
        )
        data = resp.json()
    except Exception as e:
        logger.warning(
            "lifecycle DM failed uid=%s segment=%s: %s",
            candidate.telegram_user_id,
            candidate.segment,
            e,
        )
        return {"ok": False, "error": str(e), "segment": candidate.segment}

    if not data.get("ok"):
        err = (data.get("description") or "telegram_error").strip()
        err_l = err.lower()
        from app.services.stars_bait_outreach import _DM_UNREACHABLE_ERRORS

        if any(marker in err_l for marker in _DM_UNREACHABLE_ERRORS):
            _mark_dm_unreachable(r, candidate.telegram_user_id, reason=err)
        return {
            "ok": False,
            "error": err,
            "segment": candidate.segment,
            "telegram_user_id": candidate.telegram_user_id,
        }

    _mark_sent(r, segment=candidate.segment, entity_id=candidate.entity_id)
    return {
        "ok": True,
        "sent": True,
        "kind": candidate.kind,
        "segment": candidate.segment,
        "telegram_user_id": candidate.telegram_user_id,
    }


def run_lifecycle_dm_tick(db: Session) -> dict[str, Any]:
    """Daily tick — send renewal / companion / loot re-engage DMs up to batch limit."""
    if not lifecycle_dm_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    candidates = collect_lifecycle_candidates(db)
    if not candidates:
        return {
            "ok": True,
            "sent": 0,
            "skipped": 0,
            "failed": 0,
            "candidates": 0,
            "reason": "no_candidates",
        }

    batch = dm_batch_size()
    to_send = candidates[:batch]
    if len(candidates) > batch:
        logger.warning(
            "lifecycle DM truncated %s candidates to batch cap %s — raise TBCC_LIFECYCLE_DM_BATCH",
            len(candidates),
            batch,
        )

    results: list[dict[str, Any]] = []
    sent = 0
    skipped = 0
    failed = 0

    for candidate in to_send:
        out = send_lifecycle_dm_sync(db, candidate)
        results.append(out)
        if out.get("skipped"):
            skipped += 1
        elif out.get("ok"):
            sent += 1
        else:
            failed += 1

    remaining = max(0, len(candidates) - batch)
    return {
        "ok": True,
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        "candidates": len(candidates),
        "remaining": remaining,
        "results": results,
    }
