"""Resolve local tier-card PNGs for the roll reveal beat (not content-pool media)."""

from __future__ import annotations

import os
from pathlib import Path


def loot_tier_card_dir() -> Path:
    override = (os.getenv("TBCC_LOOT_TIER_CARD_DIR") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "data" / "loot_tier_cards"


def resolve_tier_card_path(tier: int) -> Path | None:
    """
    Look for a clean art card for rarity tier 1–10.

    Filenames tried (first hit wins), under TBCC_LOOT_TIER_CARD_DIR or
    app/data/loot_tier_cards/:
      tier-{n}.png, t{n}.png, tier-{n}.webp, t{n}.webp
    """
    t = max(1, min(10, int(tier)))
    root = loot_tier_card_dir()
    if not root.is_dir():
        return None
    candidates = (
        f"tier-{t}.png",
        f"t{t}.png",
        f"tier-{t}.webp",
        f"t{t}.webp",
        f"tier-{t}.jpg",
        f"t{t}.jpg",
    )
    for name in candidates:
        path = root / name
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None
