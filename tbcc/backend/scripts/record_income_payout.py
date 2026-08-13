#!/usr/bin/env python3
"""Record an external-platform cash withdrawal in the income ledger.

  python scripts/record_income_payout.py --source linkvertise --amount 16 --notes "Bank withdrawal"
  python scripts/record_income_payout.py --source linkvertise --amount 16 --also-record-earned
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.session import SessionLocal
from app.models.income_entry import IncomeEntry
from app.services.income_ledger import SOURCE_LINKVERTISE, record_income_payout, record_manual_income


def main() -> int:
    p = argparse.ArgumentParser(description="Record external income payout (withdrawal)")
    p.add_argument("--source", default=SOURCE_LINKVERTISE, help="Income source key (linkvertise, admaven, …)")
    p.add_argument("--amount", type=float, required=True, help="USD withdrawn")
    p.add_argument("--destination", default="bank", help="bank | paypal | crypto | other")
    p.add_argument("--notes", default="", help="Operator note")
    p.add_argument(
        "--also-record-earned",
        action="store_true",
        help="If no prior earned rows for this source, also book a manual earned entry for the same amount",
    )
    p.add_argument("--execute", action="store_true", help="Write to DB (default is dry-run preview)")
    args = p.parse_args()

    db = SessionLocal()
    try:
        src = (args.source or "").strip().lower()
        prior_earned = (
            db.query(IncomeEntry)
            .filter(IncomeEntry.source == src, IncomeEntry.sync_kind != "payout")
            .count()
        )
        preview = {
            "source": src,
            "amount_usd": args.amount,
            "destination": args.destination,
            "prior_earned_entries": prior_earned,
            "also_record_earned": bool(args.also_record_earned and prior_earned == 0),
        }
        if not args.execute:
            print("DRY RUN — pass --execute to write")
            print(preview)
            return 0

        if args.also_record_earned and prior_earned == 0:
            record_manual_income(
                db,
                source=src,
                amount_usd=float(args.amount),
                notes=(args.notes or "Lifetime balance before first payout")[:500],
            )
        out = record_income_payout(
            db,
            source=src,
            amount_usd=float(args.amount),
            destination=args.destination,
            notes=args.notes or None,
        )
        db.commit()
        print({"ok": True, "payout": out, **preview})
        return 0 if out.get("ok") else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
