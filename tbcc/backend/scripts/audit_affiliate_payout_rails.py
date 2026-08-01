#!/usr/bin/env python3
"""Audit promo_affiliate_links: cash vs credits vs crypto vs funnel."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from sqlalchemy import asc

from app.database.session import SessionLocal
from app.models.promo_affiliate_link import PromoAffiliateLink
from app.services.promo_affiliate_rotation import row_placements

# Operator doctrine: cash/crypto sponsors beat platform-credit revshare.
RAIL_ORDER = ("cash", "crypto", "revshare_cash", "subscription", "revshare_unknown", "credits", "funnel", "other")

RAIL_BY_KIND: dict[str, str] = {
    "pps": "cash",
    "cpa": "cash",
    "subscription": "subscription",
    "funnel": "funnel",
    "other": "other",
}

# Label/copy hints when payout_kind alone is ambiguous.
CREDIT_HINTS = ("credit", "coin", "invite", "referral", "free ")
CRYPTO_HINTS = ("wallet", "crypto", "ton", "usdt")
CASH_REVSHARE_HINTS = ("revshare on purchases", "pps", "bangbros", "reality kings", "spicevids", "nutaku", "musebox", "nakedly", "playbun", "fapify", "pornmaker", "botynude")


def infer_rail(row: PromoAffiliateLink) -> str:
    kind = (row.payout_kind or "other").strip().lower()
    if kind in RAIL_BY_KIND:
        base = RAIL_BY_KIND[kind]
        if base != "other":
            return base
    blob = f"{row.label or ''} {row.copy_template or ''} {row.payout_detail or ''}".lower()
    if any(h in blob for h in CRYPTO_HINTS):
        return "crypto"
    if kind == "revshare":
        if any(h in blob for h in CREDIT_HINTS):
            return "credits"
        if any(h in blob for h in CASH_REVSHARE_HINTS):
            return "revshare_cash"
        return "revshare_unknown"
    if kind == "other" and ("referral" in blob or "cursor" in blob or "claude" in blob):
        return "credits"
    return "other"


def main() -> None:
    db = SessionLocal()
    try:
        rows = (
            db.query(PromoAffiliateLink)
            .filter(PromoAffiliateLink.active.is_(True))
            .order_by(asc(PromoAffiliateLink.priority_tier), asc(PromoAffiliateLink.id))
            .all()
        )
        by_rail: dict[str, list[PromoAffiliateLink]] = {r: [] for r in RAIL_ORDER}
        for row in rows:
            rail = infer_rail(row)
            by_rail.setdefault(rail, []).append(row)

        print("AFFILIATE PAYOUT RAIL AUDIT")
        print("=" * 72)
        for rail in RAIL_ORDER:
            group = by_rail.get(rail) or []
            if not group:
                continue
            print(f"\n## {rail.upper()} ({len(group)})")
            for row in group:
                placements = ",".join(row_placements(row))
                print(
                    f"  tier={row.priority_tier:2d}  id={row.id:3d}  "
                    f"kind={row.payout_kind:12s}  {row.label}"
                )
                print(f"           placements={placements}")
                if row.payout_detail:
                    print(f"           detail={row.payout_detail}")

        rot_placements = ("x_buffer", "loot_roll", "telegram_footer")
        print("\n" + "=" * 72)
        print("ROTATION POOLS (cash/crypto first — current tier order)")
        for placement in rot_placements:
            pool = [
                r
                for r in rows
                if placement in row_placements(r) and "manual_only" not in row_placements(r) or placement in row_placements(r)
            ]
            pool = [r for r in rows if placement in row_placements(r)]
            pool.sort(key=lambda r: (RAIL_ORDER.index(infer_rail(r)) if infer_rail(r) in RAIL_ORDER else 99, r.priority_tier, r.id))
            print(f"\n{placement}:")
            for i, r in enumerate(pool[:8], 1):
                print(f"  {i}. [{infer_rail(r)}] {r.label} (tier {r.priority_tier})")
            if len(pool) > 8:
                print(f"  ... +{len(pool) - 8} more")
    finally:
        db.close()


if __name__ == "__main__":
    main()
