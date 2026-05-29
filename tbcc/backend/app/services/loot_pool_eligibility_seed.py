"""Bootstrap loot_pool_eligibility from content pool names (LOOT ROOM * tiers)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.content_pool import ContentPool
from app.models.loot import LootPoolEligibility


def tier_band_for_pool_name(name: str) -> tuple[int, int] | None:
    n = (name or "").upper()
    if "SPOTLIGHT" in n:
        return 5, 7
    if any(x in n for x in ("VAULT", "RELIC", "MYTHIC")):
        return 7, 10
    if "LOOT ROOM" in n:
        return 1, 5
    return None


def seed_loot_room_pool_eligibility(db: Session) -> list[dict]:
    """Enable loot rolls for LOOT ROOM* content pools with tier bands."""
    out: list[dict] = []
    for p in db.query(ContentPool).order_by(ContentPool.id.asc()).all():
        band = tier_band_for_pool_name(getattr(p, "name", "") or "")
        if not band:
            continue
        lo, hi = band
        row = (
            db.query(LootPoolEligibility)
            .filter(LootPoolEligibility.content_pool_id == int(p.id))
            .first()
        )
        if not row:
            row = LootPoolEligibility(content_pool_id=int(p.id))
            db.add(row)
        row.loot_enabled = True
        row.base_weight = float(row.base_weight or 1.0)
        row.min_rarity_tier = lo
        row.max_rarity_tier = hi
        out.append(
            {
                "content_pool_id": int(p.id),
                "pool_name": getattr(p, "name", None),
                "min_rarity_tier": lo,
                "max_rarity_tier": hi,
            }
        )
    db.commit()
    return out
