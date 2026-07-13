"""Build and account-gate complimentary DM pulls (not paid room runs)."""

from __future__ import annotations

import random
from typing import Any

from sqlalchemy.orm import Session

from app.models.loot import LootPoolEligibility, LootPlayerMediaSeen
from app.models.media import Media
from app.services.loot_free_tease import pick_tease_lines
from app.services.loot_roll_presentation import pick_tier_flavor
from app.services.loot_operator_access import is_loot_operator
from app.services.loot_player_stats import free_pull_allowance, free_pulls_remaining, record_free_pull
from app.services.loot_referral import try_credit_referrer_for_pull
from app.services.loot_tier_catalog import FREE_PULL_LIMIT
from app.services.loot_roll_preview import _pools_for_tier, _weighted_choice
from app.services.loot_tier_catalog import (
    FREE_PULL_MAX_TIER,
    preview_summary_fields,
    roll_free_rarity_tier,
)


def build_free_pull_preview(
    db: Session,
    *,
    telegram_user_id: int,
    seed: int | None = None,
) -> dict[str, Any]:
    rng = random.Random(seed)
    operator = is_loot_operator(telegram_user_id)
    remaining_before = free_pulls_remaining(db, telegram_user_id)
    if remaining_before <= 0 and not operator:
        return {
            "ok": False,
            "reason": "free_pulls_exhausted",
            "roll_kind": "free",
            "free_pulls_used": free_pull_allowance(db, telegram_user_id),
            "free_pulls_remaining": 0,
            "free_pull_limit": free_pull_allowance(db, telegram_user_id),
        }
    if operator:
        remaining_before = max(remaining_before, 999)

    rarity = roll_free_rarity_tier(rng)
    rarity = min(rarity, FREE_PULL_MAX_TIER)

    eligible_rows = (
        db.query(LootPoolEligibility)
        .filter(LootPoolEligibility.loot_enabled.is_(True))
        .all()
    )
    tier_pools = _pools_for_tier(eligible_rows, rarity)
    eligible_pool_ids = [int(r.content_pool_id) for r in tier_pools]
    if not eligible_pool_ids:
        reason = (
            "No pools in loot_pool_eligibility with loot_enabled=true"
            if not eligible_rows
            else f"No loot-eligible pools for free-pull tier {rarity} (need pools with min/max covering 1–5)"
        )
        return {
            "ok": False,
            "reason": reason,
            "roll_kind": "free",
            "rarity_tier": rarity,
        }

    q = db.query(Media).filter(
        Media.status == "approved",
        Media.pool_id.in_(eligible_pool_ids),
    )
    seen_ids = [
        int(x[0])
        for x in db.query(LootPlayerMediaSeen.media_id)
        .filter(LootPlayerMediaSeen.telegram_user_id == int(telegram_user_id))
        .all()
    ]
    if seen_ids and not operator:
        q = q.filter(~Media.id.in_(seen_ids))

    candidates = q.all()
    if not candidates:
        return {
            "ok": False,
            "reason": "No approved media candidates (after eligibility + dedupe)",
            "roll_kind": "free",
            "rarity_tier": rarity,
        }

    allowance = free_pull_allowance(db, telegram_user_id)
    pool_w = {int(r.content_pool_id): float(r.base_weight or 1.0) for r in tier_pools}
    weights = [pool_w.get(int(m.pool_id or 0), 1.0) for m in candidates]
    picked = _weighted_choice(candidates, weights, rng)
    if not picked:
        return {"ok": False, "reason": "Failed to pick media", "roll_kind": "free"}

    summary = preview_summary_fields(rarity)
    summary["tier_flavor"] = pick_tier_flavor(rarity, rng)
    pull_number = max(1, min(FREE_PULL_LIMIT, allowance - remaining_before + 1))
    tease = pick_tease_lines(rng, 3, step=pull_number)
    return {
        "ok": True,
        "roll_kind": "free",
        "seed": seed,
        "rarity_tier": rarity,
        **summary,
        "album_size": 1,
        "modifier_slot_count": 0,
        "eligible_pool_ids": eligible_pool_ids,
        "free_pull_limit": allowance,
        "free_pulls_remaining_before": remaining_before,
        "free_pull_number": pull_number,
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
    }


def mark_free_pull_media_seen(db: Session, telegram_user_id: int, media_ids: list[int]) -> None:
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


def commit_free_pull(db: Session, telegram_user_id: int, preview: dict[str, Any]) -> dict[str, Any]:
    """Increment free pull counter and mark media seen after successful delivery."""
    if not preview.get("ok"):
        return preview
    uid = int(telegram_user_id)
    operator = is_loot_operator(uid)
    if operator:
        # Unlimited QA: do not burn the free-pull budget.
        media_ids = [int(m["id"]) for m in (preview.get("media") or []) if m.get("id") is not None]
        preview = dict(preview)
        preview["free_pulls_used"] = 0
        preview["free_pulls_remaining"] = 999
        preview["operator_unlimited"] = True
        preview["free_pull_number"] = int(preview.get("free_pull_number") or 1)
        return preview
    used_before = record_free_pull(db, uid)
    try:
        from app.services.growth_attribution import EVENT_LOOT_FREE_PULL, record_growth_attribution

        record_growth_attribution(
            db,
            event_type=EVENT_LOOT_FREE_PULL,
            telegram_user_id=uid,
            extra={"free_pull_index_before": used_before},
        )
        db.commit()
    except Exception:
        pass
    media_ids = [int(m["id"]) for m in (preview.get("media") or []) if m.get("id") is not None]
    if media_ids:
        mark_free_pull_media_seen(db, uid, media_ids)
    remaining = free_pulls_remaining(db, uid)
    credit = try_credit_referrer_for_pull(db, uid)
    preview = dict(preview)
    preview["free_pulls_used"] = used_before + 1
    preview["free_pulls_remaining"] = remaining
    if credit:
        preview["referrer_credited"] = credit
    return preview
