"""Rarity tier 1–10: names, flavor copy, zip gates, new-player luck."""

from __future__ import annotations

from typing import Any

# Unique tier names (low → high). Tune copy in dashboard later via presets.
TIER_META: dict[int, dict[str, str]] = {
    1: {
        "name": "Dust",
        "tagline": "A faint shimmer — barely worth opening.",
        "flavor": "The vault coughs up crumbs. Squint harder.",
    },
    2: {
        "name": "Glimpse",
        "tagline": "Something moved in the dark.",
        "flavor": "Not quite nothing. Not quite a drop.",
    },
    3: {
        "name": "Spark",
        "tagline": "A single spark in the loot room.",
        "flavor": "Warm enough to keep scrolling.",
    },
    4: {
        "name": "Pulse",
        "tagline": "The room notices you.",
        "flavor": "Rhythm picks up — spoilers earned.",
    },
    5: {
        "name": "Surge",
        "tagline": "Mid-tier heat — the floor leans in.",
        "flavor": "More on the reel than you expected.",
    },
    6: {
        "name": "Blaze",
        "tagline": "Spotlight energy — mixed media flex.",
        "flavor": "Photos stack, video hits — feel the pull.",
    },
    7: {
        "name": "Vault",
        "tagline": "Vault-tier pull — packs may whisper.",
        "flavor": "Rare enough that a bundle might follow.",
    },
    8: {
        "name": "Crown",
        "tagline": "Heavy crown — album density spikes.",
        "flavor": "This is why you paid attention.",
    },
    9: {
        "name": "Oracle",
        "tagline": "Near-mythic — modifiers stack.",
        "flavor": "The overseer grins. Open everything.",
    },
    10: {
        "name": "Ascension",
        "tagline": "MAX TIER — full celebration drop.",
        "flavor": "🔥 Peak dopamine. Screenshot the receipts. 🔥",
    },
}


def tier_meta(tier: int) -> dict[str, str]:
    t = max(1, min(10, int(tier)))
    return TIER_META.get(t, TIER_META[1])


def tier_display_name(tier: int) -> str:
    m = tier_meta(tier)
    return f"Tier {tier} · {m['name']}"


FREE_PULL_MAX_TIER = 5
FREE_PULL_LIMIT = 5


def roll_free_rarity_tier(rng) -> int:
    """Nerfed 1..5 weights for complimentary DM pulls (no modifiers, one item)."""
    weights = [24, 22, 20, 18, 16]  # tier 1..5
    total = sum(weights)
    target = rng.random() * total
    run = 0.0
    for i, w in enumerate(weights, start=1):
        run += w
        if run >= target:
            return i
    return 1


def roll_rarity_tier(
    rng,
    *,
    interval_rarity_shift: int = 0,
    lifetime_roll_index: int = 0,
) -> int:
    """
    Skewed 1..10 roll with optional cadence shift.
    First ~3 lifetime rolls get a soft high-tier bias that decays linearly.
    """
    # Base weights favor mid tiers; tails exist but are rarer at low end.
    weights = [12, 14, 16, 14, 12, 10, 8, 6, 4, 2]  # tier 1..10
    rolls = max(0, int(lifetime_roll_index))
    if rolls < 3:
        boost = 3 - rolls  # 3, 2, 1
        for i in range(6, 10):
            weights[i] += boost * (3 if i >= 8 else 2)
        for i in range(0, 3):
            weights[i] = max(1, weights[i] - boost * 2)

    total = sum(weights)
    target = rng.random() * total
    run = 0.0
    rolled = 1
    for i, w in enumerate(weights, start=1):
        run += w
        if run >= target:
            rolled = i
            break

    shifted = rolled + int(interval_rarity_shift or 0)
    return max(1, min(10, shifted))


def modifier_slot_probs_for_roll(
    base_probs: list[float],
    *,
    rarity_tier: int,
    lifetime_roll_index: int,
) -> list[float]:
    """Reduce modifier slots on low tiers and for brand-new players."""
    p = list(base_probs[:4])
    while len(p) < 4:
        p.append(0.0)
    rolls = max(0, int(lifetime_roll_index))
    if rolls < 3:
        # Strong bias toward zero modifier slots on first rolls.
        p[0] = min(0.92, p[0] + 0.22)
        for i in range(1, 4):
            p[i] *= 0.35
    if rarity_tier <= 3:
        p[0] = min(0.9, p[0] + 0.15)
        for i in range(1, 4):
            p[i] *= 0.5
    elif rarity_tier <= 5:
        for i in range(2, 4):
            p[i] *= 0.7
    s = sum(p) or 1.0
    return [x / s for x in p]


def modifier_weight(
    mod: Any,
    *,
    rarity_tier: int,
    lifetime_roll_index: int,
) -> float:
    w = max(0.0, float(getattr(mod, "weight_base", None) or 1.0))
    kind = (getattr(mod, "kind", None) or "").strip().lower()
    min_t = getattr(mod, "min_rarity_tier", None)
    if min_t is not None and rarity_tier < int(min_t):
        return 0.0

    if kind == "local_zip_pack":
        # ZIP bundles: very rare early; scale up with tier.
        if lifetime_roll_index < 3:
            w *= 0.04
        elif lifetime_roll_index < 8:
            w *= 0.2
        tier_mult = {1: 0.0, 2: 0.0, 3: 0.05, 4: 0.08, 5: 0.15, 6: 0.25, 7: 0.45, 8: 0.7, 9: 0.9, 10: 1.0}
        w *= tier_mult.get(rarity_tier, 0.5)
        # rarity_focus on modifier = minimum tier hint when min_rarity_tier unset
        focus = int(float(getattr(mod, "rarity_focus", None) or 1))
        if rarity_tier < max(7, focus):
            w *= 0.15
    else:
        rf = float(getattr(mod, "rarity_focus", None) or 1.0)
        if rf > 1 and rarity_tier >= 6:
            w *= rf ** 0.35

    return w


def preview_summary_fields(tier: int) -> dict[str, str]:
    m = tier_meta(tier)
    return {
        "tier_name": m["name"],
        "tier_tagline": m["tagline"],
        "tier_flavor": m["flavor"],
        "tier_display": tier_display_name(tier),
    }
