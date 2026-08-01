"""
Daily micro-pull — the free return loop.

Deliberately weaker than the 5 lifetime free pulls: tier <=2, one item, no
modifiers, heavy-mark promo class. It buys a daily habit, not a substitute for
a loot key. The streak payout is a real free pull, so the ladder still points
up toward paid rolls.
"""

from __future__ import annotations

import os
import random
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.loot import LootPlayerMediaSeen, LootPlayerStats, LootPoolEligibility
from app.models.media import Media
from app.services.loot_free_tease import pick_tease_lines
from app.services.loot_operator_access import is_loot_operator
from app.services.loot_roll_presentation import pick_tier_flavor
from app.services.loot_roll_preview import _pools_for_tier, _weighted_choice
from app.services.loot_media_deliverable import filter_roll_candidates
from app.services.loot_tier_catalog import (
    DAILY_PULL_MAX_TIER,
    FREE_PULL_MAX_TIER,
    preview_summary_fields,
    roll_daily_rarity_tier,
)


def daily_pull_enabled() -> bool:
    """Off by default — new free supply is an operator cutover, not an agent one."""
    raw = (os.getenv("TBCC_LOOT_DAILY_PULL_ENABLED") or "0").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


def daily_pull_max_tier() -> int:
    raw = (os.getenv("TBCC_LOOT_DAILY_PULL_MAX_TIER") or str(DAILY_PULL_MAX_TIER)).strip()
    try:
        return max(1, min(FREE_PULL_MAX_TIER, int(raw)))
    except ValueError:
        return DAILY_PULL_MAX_TIER


def streak_bonus_every() -> int:
    """Consecutive days that earn one bonus free pull. 0 disables the payout."""
    raw = (os.getenv("TBCC_LOOT_DAILY_STREAK_BONUS_EVERY") or "7").strip()
    try:
        return max(0, min(60, int(raw)))
    except ValueError:
        return 7


def _utc_today() -> date:
    return datetime.utcnow().date()


def _stats_row(db: Session, telegram_user_id: int) -> LootPlayerStats:
    uid = int(telegram_user_id)
    row = db.query(LootPlayerStats).filter(LootPlayerStats.telegram_user_id == uid).first()
    if not row:
        row = LootPlayerStats(
            telegram_user_id=uid,
            roll_count=0,
            free_pulls_used=0,
            bonus_free_pulls=0,
            daily_streak_days=0,
            daily_streak_best=0,
            first_roll_at=datetime.utcnow(),
        )
        db.add(row)
        db.flush()
    return row


def daily_pull_used_today(db: Session, telegram_user_id: int) -> bool:
    row = db.query(LootPlayerStats).filter(LootPlayerStats.telegram_user_id == int(telegram_user_id)).first()
    if not row or not row.daily_pull_at:
        return False
    return row.daily_pull_at.date() >= _utc_today()


def next_streak_value(last_pull_at: datetime | None, current_streak: int) -> int:
    """Streak continues only on consecutive UTC days; any gap resets to 1."""
    if not last_pull_at:
        return 1
    gap_days = (_utc_today() - last_pull_at.date()).days
    if gap_days == 1:
        return max(1, int(current_streak or 0)) + 1
    if gap_days <= 0:
        return max(1, int(current_streak or 0))
    return 1


def daily_pull_status(db: Session, telegram_user_id: int) -> dict[str, Any]:
    uid = int(telegram_user_id)
    row = db.query(LootPlayerStats).filter(LootPlayerStats.telegram_user_id == uid).first()
    streak = int(row.daily_streak_days or 0) if row else 0
    last_at = row.daily_pull_at if row else None
    claimed = daily_pull_used_today(db, uid)
    every = streak_bonus_every()
    projected = next_streak_value(last_at, streak) if not claimed else streak
    return {
        "telegram_user_id": uid,
        "enabled": daily_pull_enabled(),
        "available": daily_pull_enabled() and not claimed,
        "claimed_today": claimed,
        "max_tier": daily_pull_max_tier(),
        "streak_days": streak,
        "streak_best": int(row.daily_streak_best or 0) if row else 0,
        "streak_if_claimed": projected,
        "streak_bonus_every": every,
        "days_to_bonus": (every - (projected % every)) % every if every else None,
        "last_claim_at": last_at.isoformat() + "Z" if last_at else None,
        "next_claim_at": (
            (datetime.combine(last_at.date() + timedelta(days=1), datetime.min.time()).isoformat() + "Z")
            if claimed and last_at
            else None
        ),
    }


def build_daily_pull_preview(
    db: Session,
    *,
    telegram_user_id: int,
    seed: int | None = None,
    exclude_media_ids: list[int] | None = None,
) -> dict[str, Any]:
    uid = int(telegram_user_id)
    if not daily_pull_enabled():
        return {"ok": False, "reason": "daily_pull_disabled", "roll_kind": "daily"}

    operator = is_loot_operator(uid)
    if daily_pull_used_today(db, uid) and not operator:
        return {
            "ok": False,
            "reason": "daily_pull_already_claimed",
            "roll_kind": "daily",
            "message": "Daily pull already claimed — the room resets at 00:00 UTC.",
        }

    rng = random.Random(seed)
    rarity = roll_daily_rarity_tier(rng, max_tier=daily_pull_max_tier())

    eligible_rows = (
        db.query(LootPoolEligibility)
        .filter(LootPoolEligibility.loot_enabled.is_(True))
        .all()
    )
    tier_pools = _pools_for_tier(eligible_rows, rarity)
    eligible_pool_ids = [int(r.content_pool_id) for r in tier_pools]
    if not eligible_pool_ids:
        return {
            "ok": False,
            "reason": "no_eligible_pools",
            "roll_kind": "daily",
            "rarity_tier": rarity,
        }

    q = db.query(Media).filter(
        Media.status == "approved",
        Media.pool_id.in_(eligible_pool_ids),
    )
    seen_ids = [
        int(x[0])
        for x in db.query(LootPlayerMediaSeen.media_id)
        .filter(LootPlayerMediaSeen.telegram_user_id == uid)
        .all()
    ]
    if seen_ids and not operator:
        q = q.filter(~Media.id.in_(seen_ids))
    ban = [int(x) for x in (exclude_media_ids or []) if x is not None]
    if ban:
        q = q.filter(~Media.id.in_(ban))

    candidates = filter_roll_candidates(q.all())
    if not candidates:
        return {
            "ok": False,
            "reason": "no_media_candidates",
            "roll_kind": "daily",
            "rarity_tier": rarity,
        }

    pool_w = {int(r.content_pool_id): float(r.base_weight or 1.0) for r in tier_pools}
    weights = [pool_w.get(int(m.pool_id or 0), 1.0) for m in candidates]
    picked = _weighted_choice(candidates, weights, rng)
    if not picked:
        return {"ok": False, "reason": "pick_failed", "roll_kind": "daily"}

    status = daily_pull_status(db, uid)
    summary = preview_summary_fields(rarity)
    summary["tier_flavor"] = pick_tier_flavor(rarity, rng)
    return {
        "ok": True,
        "roll_kind": "daily",
        "seed": seed,
        "rarity_tier": rarity,
        **summary,
        "album_size": 1,
        "modifier_slot_count": 0,
        "eligible_pool_ids": eligible_pool_ids,
        "streak_days": status["streak_days"],
        "streak_if_claimed": status["streak_if_claimed"],
        "streak_bonus_every": status["streak_bonus_every"],
        "media": [
            {
                "id": int(picked.id),
                "pool_id": int(picked.pool_id or 0),
                "media_type": picked.media_type,
                "tags": picked.tags,
            }
        ],
        "modifiers": [],
        "tease_modifiers": pick_tease_lines(rng, 3, step=1),
        "daily_pull": True,
    }


def mark_daily_pull_media_seen(db: Session, telegram_user_id: int, media_ids: list[int]) -> None:
    uid = int(telegram_user_id)
    for mid in media_ids:
        exists = (
            db.query(LootPlayerMediaSeen)
            .filter(
                LootPlayerMediaSeen.telegram_user_id == uid,
                LootPlayerMediaSeen.media_id == int(mid),
            )
            .first()
        )
        if exists:
            continue
        db.add(LootPlayerMediaSeen(telegram_user_id=uid, media_id=int(mid)))
    db.commit()


def commit_daily_pull(db: Session, telegram_user_id: int, preview: dict[str, Any]) -> dict[str, Any]:
    """Stamp the claim, advance the streak, and pay the streak bonus when it lands."""
    if not preview.get("ok"):
        return preview

    uid = int(telegram_user_id)
    out = dict(preview)

    if is_loot_operator(uid):
        out["operator_unlimited"] = True
        return out

    row = _stats_row(db, uid)
    streak = next_streak_value(row.daily_pull_at, int(row.daily_streak_days or 0))
    row.daily_pull_at = datetime.utcnow()
    row.daily_streak_days = streak
    row.daily_streak_best = max(int(row.daily_streak_best or 0), streak)

    every = streak_bonus_every()
    bonus_awarded = 0
    if every and streak % every == 0:
        row.bonus_free_pulls = int(row.bonus_free_pulls or 0) + 1
        bonus_awarded = 1
    db.commit()

    try:
        from app.services.growth_attribution import EVENT_LOOT_FREE_PULL, record_growth_attribution

        record_growth_attribution(
            db,
            event_type=EVENT_LOOT_FREE_PULL,
            telegram_user_id=uid,
            extra={
                "roll_kind": "daily",
                "rarity_tier": preview.get("rarity_tier"),
                "streak_days": streak,
                "bonus_free_pulls_awarded": bonus_awarded,
            },
        )
        db.commit()
    except Exception:
        pass

    media_ids = [int(m["id"]) for m in (preview.get("media") or []) if m.get("id") is not None]
    if media_ids:
        mark_daily_pull_media_seen(db, uid, media_ids)

    out["streak_days"] = streak
    out["streak_best"] = int(row.daily_streak_best or 0)
    out["bonus_free_pulls_awarded"] = bonus_awarded
    out["daily_claimed_at"] = row.daily_pull_at.isoformat() if row.daily_pull_at else None
    return out
