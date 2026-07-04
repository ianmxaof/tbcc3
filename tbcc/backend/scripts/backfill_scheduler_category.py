#!/usr/bin/env python3
"""
Backfill scheduler_category on scheduled_text_posts from name patterns.

Usage:
  cd tbcc/backend
  py -3.13 scripts/backfill_scheduler_category.py
  py -3.13 scripts/backfill_scheduler_category.py --execute
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.scheduler_category import apply_scheduler_category, infer_scheduler_category


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="Backfill scheduler_category on scheduled posts")
    p.add_argument("--execute", action="store_true", help="Write changes (default dry-run)")
    args = p.parse_args()

    db = SessionLocal()
    updated = unchanged = 0
    by_category: dict[str, int] = {}
    try:
        rows = db.query(ScheduledTextPost).order_by(ScheduledTextPost.id.asc()).all()
        for row in rows:
            inferred = infer_scheduler_category(row.name)
            by_category[inferred] = by_category.get(inferred, 0) + 1
            if row.scheduler_category == inferred:
                unchanged += 1
                continue
            if args.execute:
                apply_scheduler_category(row, inferred)
            updated += 1

        if args.execute:
            db.commit()
        else:
            db.rollback()

        mode = "updated" if args.execute else "would_update"
        print(f"{mode}: {updated} rows ({unchanged} already correct, {len(rows)} total)")
        for cat, count in sorted(by_category.items()):
            print(f"  {cat}: {count}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
