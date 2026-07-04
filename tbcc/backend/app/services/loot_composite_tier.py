"""Derive displayed rarity tier from dice roll + what was actually drawn."""

from __future__ import annotations

from typing import Any

from app.models.loot import LootPoolEligibility
from app.models.media import Media


def pool_band_midpoint(row: LootPoolEligibility | None) -> float:
    if not row:
        return 5.0
    lo = int(row.min_rarity_tier) if row.min_rarity_tier is not None else 1
    hi = int(row.max_rarity_tier) if row.max_rarity_tier is not None else 10
    return (lo + hi) / 2.0


def compute_composite_tier(
    base_roll: int,
    picked_media: list[Media],
    pool_eligibility: dict[int, LootPoolEligibility],
) -> int:
    """
    Blend initial dice tier with average pool band of picks, album volume, and pool diversity.
    """
    base = max(1, min(10, int(base_roll)))
    if not picked_media:
        return base

    mids: list[float] = []
    for m in picked_media:
        pid = int(m.pool_id or 0)
        mids.append(pool_band_midpoint(pool_eligibility.get(pid)))

    avg_pool = sum(mids) / len(mids)
    volume = len(picked_media)
    diversity = len({int(m.pool_id or 0) for m in picked_media})

    score = (
        0.30 * base
        + 0.42 * avg_pool
        + 0.18 * volume
        + 0.10 * min(10.0, diversity * 1.8)
    )
    final = int(round(score))
    return max(1, min(10, final))


def composite_tier_fields(
    base_roll: int,
    final_tier: int,
    picked_media: list[Media],
    pool_eligibility: dict[int, LootPoolEligibility],
) -> dict[str, Any]:
    """Debug / API fields explaining the composite score."""
    pool_ids = sorted({int(m.pool_id or 0) for m in picked_media})
    bands = []
    for pid in pool_ids:
        row = pool_eligibility.get(pid)
        if row:
            lo = int(row.min_rarity_tier or 1)
            hi = int(row.max_rarity_tier or 10)
            bands.append({"pool_id": pid, "min_tier": lo, "max_tier": hi})
    return {
        "base_roll_tier": int(base_roll),
        "rarity_tier": int(final_tier),
        "composite_pool_ids": pool_ids,
        "composite_pool_bands": bands,
        "composite_media_count": len(picked_media),
    }
