"""
Seed companion reveal credit packs into subscription_plans.

  cd tbcc/backend && py -3.13 scripts/seed_companion_credit_packs.py --execute
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.models.subscription_plan import SubscriptionPlan
from app.data.companion_credit_packs import COMPANION_CREDIT_PACKS

STARS_USD = float(os.getenv("TBCC_STARS_USD_PER_STAR") or "0.012")


def _usd(stars: int) -> float:
    return round(stars * STARS_USD, 2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed companion credit pack plans")
    parser.add_argument("--execute", action="store_true", help="Write to DB (default dry-run)")
    args = parser.parse_args()

    db = SessionLocal()
    report: list[dict] = []
    try:
        for pack in COMPANION_CREDIT_PACKS:
            existing = (
                db.query(SubscriptionPlan).filter(SubscriptionPlan.name == pack.plan_name).first()
            )
            row = {
                "name": pack.plan_name,
                "sku": pack.sku,
                "credits": pack.credit_units,
                "stars": pack.price_stars,
                "usd_crypto": pack.price_usd,
                "status": "exists" if existing else "create",
            }
            report.append(row)
            if existing or not args.execute:
                continue
            db.add(
                SubscriptionPlan(
                    name=pack.plan_name,
                    price_stars=pack.price_stars,
                    duration_days=0,
                    channel_id=None,
                    description=pack.blurb,
                    description_variations_json=json.dumps([]),
                    is_active=True,
                    product_type="companion_credits",
                    bot_section="companion",
                    nowpayments_price_usd=float(pack.price_usd),
                    nowpayments_allow_any_currency=True,
                )
            )
        if args.execute:
            db.commit()
    finally:
        db.close()

    print(json.dumps({"ok": True, "execute": args.execute, "plans": report}, indent=2))


if __name__ == "__main__":
    main()
