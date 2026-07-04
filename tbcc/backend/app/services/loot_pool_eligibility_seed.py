"""Bootstrap loot_pool_eligibility from content pool names and approved media."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.data.aof_network import AOF_NETWORK_CHANNELS
from app.models.content_pool import ContentPool
from app.models.loot import LootPoolEligibility
from app.models.media import Media

# Network channel key → rarity band for loot rolls (overlapping bands cover tiers 1–10).
_NETWORK_KEY_TIER_BANDS: dict[str, tuple[int, int]] = {
    "ai": (1, 5),
    "ass": (1, 5),
    "big_tits": (1, 5),
    "blowjob": (1, 5),
    "milf": (1, 5),
    "taboo": (1, 5),
    "voyeur": (5, 7),
    "abg": (5, 7),
    "goon": (5, 8),
    "bop": (5, 8),
    "main": (7, 10),
    "packs": (8, 10),
}

_POOL_NAME_TO_NETWORK_KEY: dict[str, str] = {
    ch.pool_name.strip().upper(): ch.key for ch in AOF_NETWORK_CHANNELS
}


def tier_band_for_pool_name(name: str) -> tuple[int, int] | None:
    n = (name or "").strip().upper()
    if not n:
        return None

    net_key = _POOL_NAME_TO_NETWORK_KEY.get(n)
    if net_key:
        return _NETWORK_KEY_TIER_BANDS.get(net_key)

    if "SPOTLIGHT" in n:
        return 5, 7
    if any(x in n for x in ("VAULT", "RELIC", "MYTHIC")):
        return 7, 10
    if "LOOT ROOM" in n:
        if "SPOTLIGHT" in n:
            return 5, 7
        if any(x in n for x in ("VAULT", "RELIC", "MYTHIC")):
            return 7, 10
        return 1, 5

    if "PACK" in n and "PROMO" in n:
        return 8, 10
    if "MAIN" in n and "GROUP" in n:
        return 7, 10
    if any(x in n for x in ("VOYEUR", "PUBLIC")):
        return 5, 7
    if any(x in n for x in ("ABG", "LBFM")):
        return 5, 7
    if "GOON" in n:
        return 5, 8
    if "BOP" in n:
        return 5, 8
    if n.endswith(" POOL") or " POOL" in n:
        return 1, 5
    return None


def _upsert_eligibility(
    db: Session,
    *,
    pool_id: int,
    pool_name: str | None,
    lo: int,
    hi: int,
    loot_enabled: bool,
) -> dict:
    row = (
        db.query(LootPoolEligibility)
        .filter(LootPoolEligibility.content_pool_id == int(pool_id))
        .first()
    )
    if not row:
        row = LootPoolEligibility(content_pool_id=int(pool_id))
        db.add(row)
    row.loot_enabled = bool(loot_enabled)
    row.base_weight = float(row.base_weight or 1.0)
    row.min_rarity_tier = lo
    row.max_rarity_tier = hi
    return {
        "content_pool_id": int(pool_id),
        "pool_name": pool_name,
        "min_rarity_tier": lo,
        "max_rarity_tier": hi,
        "loot_enabled": bool(loot_enabled),
    }


def seed_loot_room_pool_eligibility(db: Session) -> list[dict]:
    """Enable loot rolls for LOOT ROOM* content pools with tier bands."""
    out: list[dict] = []
    for p in db.query(ContentPool).order_by(ContentPool.id.asc()).all():
        band = tier_band_for_pool_name(getattr(p, "name", "") or "")
        if not band:
            continue
        lo, hi = band
        out.append(_upsert_eligibility(db, pool_id=int(p.id), pool_name=p.name, lo=lo, hi=hi, loot_enabled=True))
    db.commit()
    return out


def seed_content_pool_loot_eligibility(
    db: Session,
    *,
    min_approved_media: int = 1,
    disable_empty_loot_room_pools: bool = True,
) -> dict:
    """
    Map existing content pools (with approved media) into loot_pool_eligibility so
    rolls can draw from the live library until dedicated LOOT ROOM pools are stocked.
    """
    media_counts = dict(
        db.query(Media.pool_id, func.count(Media.id))
        .filter(Media.status == "approved", Media.pool_id.isnot(None))
        .group_by(Media.pool_id)
        .all()
    )

    enabled: list[dict] = []
    skipped: list[dict] = []
    disabled: list[dict] = []

    for p in db.query(ContentPool).order_by(ContentPool.id.asc()).all():
        name = (getattr(p, "name", "") or "").strip()
        count = int(media_counts.get(int(p.id), 0))
        band = tier_band_for_pool_name(name)

        if (name.upper().startswith("LOOT ROOM") and count < min_approved_media
                and disable_empty_loot_room_pools):
            row = (
                db.query(LootPoolEligibility)
                .filter(LootPoolEligibility.content_pool_id == int(p.id))
                .first()
            )
            if row and row.loot_enabled:
                disabled.append(
                    _upsert_eligibility(
                        db,
                        pool_id=int(p.id),
                        pool_name=name,
                        lo=int(row.min_rarity_tier or 1),
                        hi=int(row.max_rarity_tier or 10),
                        loot_enabled=False,
                    )
                )
            continue

        if count < min_approved_media or not band:
            if count > 0 and not band:
                skipped.append({"content_pool_id": int(p.id), "pool_name": name, "reason": "no_tier_band"})
            continue

        lo, hi = band
        enabled.append(
            _upsert_eligibility(
                db,
                pool_id=int(p.id),
                pool_name=name,
                lo=lo,
                hi=hi,
                loot_enabled=True,
            )
        )

    db.commit()
    coverage = tier_coverage_report(db)
    return {
        "enabled": enabled,
        "disabled_empty_loot_room": disabled,
        "skipped": skipped,
        "tier_coverage": coverage,
    }


def tier_coverage_report(db: Session) -> dict:
    """For each rarity tier 1–10, count eligible pools that contain approved media."""
    media_counts = dict(
        db.query(Media.pool_id, func.count(Media.id))
        .filter(Media.status == "approved", Media.pool_id.isnot(None))
        .group_by(Media.pool_id)
        .all()
    )
    tiers = {t: [] for t in range(1, 11)}
    rows = db.query(LootPoolEligibility).filter(LootPoolEligibility.loot_enabled.is_(True)).all()
    for row in rows:
        pid = int(row.content_pool_id)
        if int(media_counts.get(pid, 0)) <= 0:
            continue
        lo = int(row.min_rarity_tier or 1)
        hi = int(row.max_rarity_tier or 10)
        p = db.query(ContentPool).filter(ContentPool.id == pid).first()
        pname = getattr(p, "name", None) if p else None
        for t in range(lo, hi + 1):
            tiers[t].append({"content_pool_id": pid, "pool_name": pname})
    missing = [t for t, pools in tiers.items() if not pools]
    return {"by_tier": tiers, "missing_tiers": missing, "all_tiers_covered": not missing}
