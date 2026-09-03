from __future__ import annotations

import json
import logging
import os
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
from app.models.content_pool import ContentPool
from app.models.media import Media
from app.services.loot_composite_tier import compute_composite_tier, composite_tier_fields
from app.services.loot_media_deliverable import filter_roll_candidates, prefer_local_byte_candidates
from app.services.loot_operator_access import is_loot_operator
from app.services.loot_player_modifiers import seen_modifier_ids
from app.services.loot_player_stats import get_lifetime_roll_index
from app.services.loot_roll_presentation import pick_tier_flavor
from app.services.loot_tier_catalog import (
    modifier_slot_probs_for_roll,
    modifier_weight,
    preview_summary_fields,
    roll_rarity_tier,
)

logger = logging.getLogger(__name__)


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


def loot_album_max_items() -> int:
    """Paid rolls used to send up to 12 files; that stalls Telegram downloads past 10s."""
    raw = (os.getenv("TBCC_LOOT_ALBUM_MAX") or "3").strip()
    try:
        return max(1, min(12, int(raw)))
    except ValueError:
        return 3


def kick_loot_stock_background() -> None:
    """Queue SENT VAULT restock on Celery. Never scan Telegram on the player /roll path."""
    try:
        from app.workers.sent_vault_lane_refill_worker import refill_dry_lanes_from_sent_vault_task

        refill_dry_lanes_from_sent_vault_task.delay()
    except Exception:
        logger.debug("loot stock background kick skipped", exc_info=True)


def _pool_names_for_rows(db: Session, rows: list[LootPoolEligibility]) -> dict[int, str]:
    ids = [int(r.content_pool_id) for r in rows]
    if not ids:
        return {}
    return {
        int(p.id): (p.name or "")
        for p in db.query(ContentPool).filter(ContentPool.id.in_(ids)).all()
    }


def _pools_for_tier(
    eligible_rows: list[LootPoolEligibility],
    rarity: int,
    pool_names: dict[int, str] | None = None,
) -> list[LootPoolEligibility]:
    """
    Pools eligible for a rarity roll.

    Prefer dedicated LOOT ROOM* clones when those rows are enabled so public
    channel posting does not empty the same deck the bot draws from.
    Otherwise shared-library mode: every loot_enabled row (bands are informational).
    """
    enabled = [r for r in eligible_rows if bool(getattr(r, "loot_enabled", True))]
    if not enabled:
        out: list[LootPoolEligibility] = []
        for r in eligible_rows:
            lo = int(r.min_rarity_tier) if r.min_rarity_tier is not None else 1
            hi = int(r.max_rarity_tier) if r.max_rarity_tier is not None else 10
            if lo <= int(rarity) <= hi:
                out.append(r)
        return out or list(eligible_rows)
    names = pool_names or {}
    dedicated = [
        r
        for r in enabled
        if str(names.get(int(r.content_pool_id), "")).upper().startswith("LOOT ROOM")
    ]
    if dedicated:
        return dedicated
    return enabled


def _load_roll_candidates(
    db: Session,
    pool_ids: list[int],
    *,
    seen_ids: list[int],
    skip_seen: bool,
    exclude_ids: list[int] | None = None,
) -> list[Media]:
    if not pool_ids:
        return []
    q = db.query(Media).filter(
        Media.status == "approved",
        Media.pool_id.in_(pool_ids),
    )
    if seen_ids and skip_seen:
        q = q.filter(~Media.id.in_(seen_ids))
    ban = [int(x) for x in (exclude_ids or []) if x is not None]
    if ban:
        q = q.filter(~Media.id.in_(ban))
    return prefer_local_byte_candidates(filter_roll_candidates(q.all()))


def _candidates_prefer_dedicated_then_shared(
    db: Session,
    eligible_rows: list[LootPoolEligibility],
    rarity: int,
    *,
    seen_ids: list[int],
    skip_seen: bool,
    exclude_ids: list[int] | None = None,
) -> tuple[list[LootPoolEligibility], list[int], list[Media]]:
    names = _pool_names_for_rows(db, eligible_rows)
    tier_pools = _pools_for_tier(eligible_rows, rarity, pool_names=names)
    pool_ids = [int(r.content_pool_id) for r in tier_pools]
    candidates = _load_roll_candidates(
        db, pool_ids, seen_ids=seen_ids, skip_seen=skip_seen, exclude_ids=exclude_ids
    )
    enabled = [r for r in eligible_rows if bool(getattr(r, "loot_enabled", True))]
    enabled_ids = [int(r.content_pool_id) for r in enabled]
    if not candidates and enabled_ids and set(enabled_ids) != set(pool_ids):
        tier_pools = enabled or tier_pools
        pool_ids = enabled_ids
        candidates = _load_roll_candidates(
            db, pool_ids, seen_ids=seen_ids, skip_seen=skip_seen, exclude_ids=exclude_ids
        )
    if not candidates:
        kick_loot_stock_background()
    return tier_pools, pool_ids, candidates


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
    base_rarity = roll_rarity_tier(
        rng,
        interval_rarity_shift=int(tier_row.rarity_shift or 0),
        lifetime_roll_index=lifetime_idx,
    )
    bonus_draws = int(tier_row.bonus_album_draws or 0)
    album_size = min(loot_album_max_items(), base_rarity + bonus_draws)

    eligible_rows = (
        db.query(LootPoolEligibility)
        .filter(LootPoolEligibility.loot_enabled.is_(True))
        .all()
    )
    if not eligible_rows:
        return {
            "ok": False,
            "reason": (
                "No pools in loot_pool_eligibility with loot_enabled=true. "
                "Dashboard → Loot overseer: seed content pools (POST /loot/seed-content-pool-eligibility) "
                "or loot room pools (POST /loot/seed-loot-room-eligibility) "
                "or POST /loot/pool-eligibility per content pool."
            ),
            "interval_code": tier_row.code,
            "rarity_tier": base_rarity,
            "base_roll_tier": base_rarity,
        }

    seen_ids: list[int] = []
    skip_seen = bool(telegram_user_id and not is_loot_operator(telegram_user_id))
    if telegram_user_id and skip_seen:
        seen_ids = [
            int(x[0])
            for x in db.query(LootPlayerMediaSeen.media_id)
            .filter(LootPlayerMediaSeen.telegram_user_id == int(telegram_user_id))
            .all()
        ]

    tier_pools, eligible_pool_ids, candidates = _candidates_prefer_dedicated_then_shared(
        db,
        eligible_rows,
        base_rarity,
        seen_ids=seen_ids,
        skip_seen=skip_seen,
    )
    pool_elig_map = {int(r.content_pool_id): r for r in eligible_rows}
    if not eligible_pool_ids:
        return {
            "ok": False,
            "reason": (
                f"No loot-eligible pools for rarity tier {base_rarity} "
                f"(check min_rarity_tier / max_rarity_tier on loot_pool_eligibility rows)"
            ),
            "interval_code": tier_row.code,
            "rarity_tier": base_rarity,
            "base_roll_tier": base_rarity,
        }
    if not candidates:
        return {
            "ok": False,
            "reason": "No approved media candidates (after eligibility + dedupe filter)",
            "interval_code": tier_row.code,
            "rarity_tier": base_rarity,
            "base_roll_tier": base_rarity,
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

    rarity = compute_composite_tier(base_rarity, picked_media, pool_elig_map)

    slot_probs = modifier_slot_probs_for_roll(
        slot_probs_base,
        rarity_tier=rarity,
        lifetime_roll_index=lifetime_idx,
    )
    slot_count = _weighted_choice([0, 1, 2, 3], slot_probs, rng)
    slot_count = int(slot_count or 0)

    mods = db.query(LootModifier).filter(LootModifier.active.is_(True)).all()
    if telegram_user_id:
        already = seen_modifier_ids(db, int(telegram_user_id))
        if already:
            mods = [m for m in mods if int(m.id) not in already]
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
    summary["tier_flavor"] = pick_tier_flavor(rarity, rng)
    composite_meta = composite_tier_fields(base_rarity, rarity, picked_media, pool_elig_map)
    return {
        "ok": True,
        "seed": seed,
        "interval_code": tier_row.code,
        "interval_seconds": int(tier_row.drop_interval_seconds or 0),
        "bonus_album_draws": int(tier_row.bonus_album_draws or 0),
        "lifetime_roll_index": lifetime_idx,
        **summary,
        **composite_meta,
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
