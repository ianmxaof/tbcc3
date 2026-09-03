"""VIP subscriber daily god roll — high-tier complimentary pull (1/day)."""

from __future__ import annotations

import os
import random
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.loot import LootPlayerMediaSeen, LootPlayerStats, LootPoolEligibility
from app.services.loot_free_tease import pick_tease_lines
from app.services.loot_player_stats import get_lifetime_roll_index
from app.services.loot_roll_presentation import pick_tier_flavor
from app.services.loot_roll_preview import _candidates_prefer_dedicated_then_shared, _weighted_choice
from app.services.loot_tier_catalog import preview_summary_fields, roll_rarity_tier
from app.services.subscription_access import is_aof_vip_subscriber


def vip_daily_pull_enabled() -> bool:
    raw = (os.getenv("TBCC_VIP_DAILY_GOD_ROLL_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def vip_daily_min_tier() -> int:
    raw = (os.getenv("TBCC_VIP_DAILY_MIN_TIER") or "7").strip()
    try:
        return max(5, min(10, int(raw)))
    except ValueError:
        return 7


def _stats_row(db: Session, telegram_user_id: int) -> LootPlayerStats:
    uid = int(telegram_user_id)
    row = db.query(LootPlayerStats).filter(LootPlayerStats.telegram_user_id == uid).first()
    if not row:
        row = LootPlayerStats(
            telegram_user_id=uid,
            roll_count=0,
            free_pulls_used=0,
            bonus_free_pulls=0,
            first_roll_at=datetime.utcnow(),
        )
        db.add(row)
        db.flush()
    return row


def _utc_today() -> date:
    return datetime.utcnow().date()


def vip_daily_pull_used_today(db: Session, telegram_user_id: int) -> bool:
    row = db.query(LootPlayerStats).filter(LootPlayerStats.telegram_user_id == int(telegram_user_id)).first()
    if not row or not row.vip_daily_pull_at:
        return False
    return row.vip_daily_pull_at.date() >= _utc_today()


def vip_daily_pull_available(db: Session, telegram_user_id: int) -> bool:
    if not vip_daily_pull_enabled():
        return False
    if not is_aof_vip_subscriber(db, int(telegram_user_id)):
        return False
    return not vip_daily_pull_used_today(db, int(telegram_user_id))


def roll_vip_daily_rarity_tier(rng, db: Session, telegram_user_id: int) -> int:
    """Skewed high-tier roll for VIP daily god roll."""
    floor = vip_daily_min_tier()
    lifetime = get_lifetime_roll_index(db, int(telegram_user_id))
    rolled = roll_rarity_tier(rng, interval_rarity_shift=2, lifetime_roll_index=lifetime)
    return max(floor, min(10, rolled))


def build_vip_daily_pull_preview(
    db: Session,
    *,
    telegram_user_id: int,
    seed: int | None = None,
) -> dict[str, Any]:
    uid = int(telegram_user_id)
    if not vip_daily_pull_enabled():
        return {"ok": False, "reason": "vip_daily_disabled", "roll_kind": "vip_daily"}
    if not is_aof_vip_subscriber(db, uid):
        return {
            "ok": False,
            "reason": "not_vip_subscriber",
            "roll_kind": "vip_daily",
            "message": "AOF VIP subscription required — @aofsubscriptions_bot /subscribe",
        }
    if vip_daily_pull_used_today(db, uid):
        return {
            "ok": False,
            "reason": "vip_daily_already_claimed",
            "roll_kind": "vip_daily",
            "message": "Daily god roll already claimed today — back tomorrow.",
        }

    rng = random.Random(seed)
    rarity = roll_vip_daily_rarity_tier(rng, db, uid)

    eligible_rows = (
        db.query(LootPoolEligibility)
        .filter(LootPoolEligibility.loot_enabled.is_(True))
        .all()
    )
    seen_ids = [
        int(x[0])
        for x in db.query(LootPlayerMediaSeen.media_id)
        .filter(LootPlayerMediaSeen.telegram_user_id == uid)
        .all()
    ]
    tier_pools, eligible_pool_ids, candidates = _candidates_prefer_dedicated_then_shared(
        db,
        eligible_rows,
        rarity,
        seen_ids=seen_ids,
        skip_seen=True,
    )
    if not eligible_pool_ids:
        return {
            "ok": False,
            "reason": "no_eligible_pools",
            "roll_kind": "vip_daily",
            "rarity_tier": rarity,
        }
    if not candidates:
        return {
            "ok": False,
            "reason": "no_media_candidates",
            "roll_kind": "vip_daily",
            "rarity_tier": rarity,
        }

    pool_w = {int(r.content_pool_id): float(r.base_weight or 1.0) for r in tier_pools}
    weights = [pool_w.get(int(m.pool_id or 0), 1.0) for m in candidates]
    picked = _weighted_choice(candidates, weights, rng)
    if not picked:
        return {"ok": False, "reason": "pick_failed", "roll_kind": "vip_daily"}

    summary = preview_summary_fields(rarity)
    summary["tier_flavor"] = pick_tier_flavor(rarity, rng)
    tease = pick_tease_lines(rng, 3, step=10)
    return {
        "ok": True,
        "roll_kind": "vip_daily",
        "seed": seed,
        "rarity_tier": rarity,
        **summary,
        "album_size": 1,
        "modifier_slot_count": 0,
        "eligible_pool_ids": eligible_pool_ids,
        "media": [
            {
                "id": int(picked.id),
                "pool_id": int(picked.pool_id or 0),
                "media_type": picked.media_type,
                "tags": picked.tags,
            }
        ],
        "modifiers": [],
        "tease_modifiers": tease,
        "vip_daily": True,
    }


def mark_vip_daily_media_seen(db: Session, telegram_user_id: int, media_ids: list[int]) -> None:
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


def commit_vip_daily_pull(db: Session, telegram_user_id: int, preview: dict[str, Any]) -> dict[str, Any]:
    if not preview.get("ok"):
        return preview
    row = _stats_row(db, int(telegram_user_id))
    row.vip_daily_pull_at = datetime.utcnow()
    db.commit()
    try:
        from app.services.growth_attribution import EVENT_LOOT_FREE_PULL, record_growth_attribution

        record_growth_attribution(
            db,
            event_type=EVENT_LOOT_FREE_PULL,
            telegram_user_id=int(telegram_user_id),
            extra={"roll_kind": "vip_daily", "rarity_tier": preview.get("rarity_tier")},
        )
        db.commit()
    except Exception:
        pass
    media_ids = [int(m["id"]) for m in (preview.get("media") or []) if m.get("id") is not None]
    if media_ids:
        mark_vip_daily_media_seen(db, int(telegram_user_id), media_ids)
    out = dict(preview)
    out["vip_daily_claimed_at"] = row.vip_daily_pull_at.isoformat() if row.vip_daily_pull_at else None
    return out
