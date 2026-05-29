from __future__ import annotations

import json
import random
from typing import Any

from sqlalchemy.orm import Session

from app.models.loot import (
    LootGameConfig,
    LootIntervalTier,
    LootModifier,
    LootPlayerMediaSeen,
    LootPoolEligibility,
)
from app.models.media import Media
from app.services.loot_player_stats import get_lifetime_roll_index
from app.services.loot_tier_catalog import (
    modifier_slot_probs_for_roll,
    modifier_weight,
    preview_summary_fields,
    roll_rarity_tier,
)


def _normalize_probs(raw_json: str | None) -> list[float]:
    try:
        arr = json.loads(raw_json or "[]")
        vals = [max(0.0, float(x)) for x in arr[:4]]
        while len(vals) < 4:
            vals.append(0.0)
        s = sum(vals)
        if s <= 0:
            return [0.55, 0.28, 0.12, 0.05]
        return [x / s for x in vals]
    except Exception:
        return [0.55, 0.28, 0.12, 0.05]


def _weighted_choice(items: list[Any], weights: list[float], rng: random.Random):
    if not items:
        return None
    total = sum(max(0.0, float(w)) for w in weights)
    if total <= 0:
        return None
    target = rng.random() * total
    run = 0.0
    for item, w in zip(items, weights):
        run += max(0.0, float(w))
        if run >= target:
            return item
    return items[-1]


def _pools_for_tier(eligible_rows: list[LootPoolEligibility], rarity: int) -> list[LootPoolEligibility]:
    out: list[LootPoolEligibility] = []
    for r in eligible_rows:
        lo = int(r.min_rarity_tier) if r.min_rarity_tier is not None else 1
        hi = int(r.max_rarity_tier) if r.max_rarity_tier is not None else 10
        if lo <= rarity <= hi:
            out.append(r)
    return out or list(eligible_rows)


def build_roll_preview(
    db: Session,
    *,
    telegram_user_id: int | None = None,
    interval_code: str = "m30",
    seed: int | None = None,
) -> dict[str, Any]:
    rng = random.Random(seed)

    cfg = db.query(LootGameConfig).order_by(LootGameConfig.id.asc()).first()
    slot_probs_base = _normalize_probs(cfg.p_modifier_slots_json if cfg else None)
    tier_row = (
        db.query(LootIntervalTier)
        .filter(LootIntervalTier.code == interval_code.strip().lower())
        .first()
    )
    if not tier_row:
        tier_row = db.query(LootIntervalTier).order_by(LootIntervalTier.id.asc()).first()
    if not tier_row:
        raise ValueError("loot_interval_tiers is empty; run alembic upgrade head")

    lifetime_idx = get_lifetime_roll_index(db, telegram_user_id)
    rarity = roll_rarity_tier(
        rng,
        interval_rarity_shift=int(tier_row.rarity_shift or 0),
        lifetime_roll_index=lifetime_idx,
    )
    album_size = rarity

    eligible_rows = (
        db.query(LootPoolEligibility)
        .filter(LootPoolEligibility.loot_enabled.is_(True))
        .all()
    )
    tier_pools = _pools_for_tier(eligible_rows, rarity)
    eligible_pool_ids = [int(r.content_pool_id) for r in tier_pools]
    if not eligible_pool_ids:
        if not eligible_rows:
            reason = (
                "No pools in loot_pool_eligibility with loot_enabled=true. "
                "Dashboard → Loot overseer: seed loot room pools (POST /loot/seed-loot-room-eligibility) "
                "or POST /loot/pool-eligibility per content pool."
            )
        else:
            reason = (
                f"No loot-eligible pools for rarity tier {rarity} "
                f"(check min_rarity_tier / max_rarity_tier on loot_pool_eligibility rows)"
            )
        return {
            "ok": False,
            "reason": reason,
            "interval_code": tier_row.code,
            "rarity_tier": rarity,
        }

    q = db.query(Media).filter(
        Media.status == "approved",
        Media.pool_id.in_(eligible_pool_ids),
    )
    if telegram_user_id:
        seen_ids = [
            int(x[0])
            for x in db.query(LootPlayerMediaSeen.media_id)
            .filter(LootPlayerMediaSeen.telegram_user_id == int(telegram_user_id))
            .all()
        ]
        if seen_ids:
            q = q.filter(~Media.id.in_(seen_ids))

    candidates = q.all()
    if not candidates:
        return {
            "ok": False,
            "reason": "No approved media candidates (after eligibility + dedupe filter)",
            "interval_code": tier_row.code,
            "rarity_tier": rarity,
        }

    pool_w = {int(r.content_pool_id): float(r.base_weight or 1.0) for r in tier_pools}
    remaining = list(candidates)
    picked_media: list[Media] = []
    for _ in range(min(album_size, len(remaining))):
        weights = [pool_w.get(int(m.pool_id or 0), 1.0) for m in remaining]
        m = _weighted_choice(remaining, weights, rng)
        if not m:
            break
        picked_media.append(m)
        remaining = [x for x in remaining if x.id != m.id]

    slot_probs = modifier_slot_probs_for_roll(
        slot_probs_base,
        rarity_tier=rarity,
        lifetime_roll_index=lifetime_idx,
    )
    slot_count = _weighted_choice([0, 1, 2, 3], slot_probs, rng)
    slot_count = int(slot_count or 0)

    mods = db.query(LootModifier).filter(LootModifier.active.is_(True)).all()
    picked_mods: list[LootModifier] = []
    rem_mods = list(mods)
    for slot_i in range(slot_count):
        if not rem_mods:
            break
        weights = [
            modifier_weight(
                m,
                rarity_tier=rarity,
                lifetime_roll_index=lifetime_idx,
            )
            for m in rem_mods
        ]
        if sum(weights) <= 0:
            break
        m = _weighted_choice(rem_mods, weights, rng)
        if not m:
            break
        picked_mods.append(m)
        rem_mods = [x for x in rem_mods if x.id != m.id]

    summary = preview_summary_fields(rarity)
    return {
        "ok": True,
        "seed": seed,
        "interval_code": tier_row.code,
        "interval_seconds": int(tier_row.drop_interval_seconds or 0),
        "bonus_album_draws": int(tier_row.bonus_album_draws or 0),
        "rarity_tier": rarity,
        "lifetime_roll_index": lifetime_idx,
        **summary,
        "album_size": len(picked_media),
        "modifier_slot_count": slot_count,
        "eligible_pool_ids": eligible_pool_ids,
        "media": [
            {
                "id": int(m.id),
                "pool_id": int(m.pool_id or 0),
                "media_type": m.media_type,
                "tags": m.tags,
            }
            for m in picked_media
        ],
        "modifiers": [
            {
                "id": int(m.id),
                "kind": m.kind,
                "label": m.label,
                "target_url": m.target_url,
            }
            for m in picked_mods
        ],
    }
