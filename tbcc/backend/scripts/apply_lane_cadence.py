#!/usr/bin/env python3
"""Idempotent cadence apply for CADENCE track I2: bump the 11 AOF content-lane
scheduled_text_posts.interval_minutes to a target (default 288 = ~5 posts/day).

Dry-run by default; --execute writes. Re-running after apply is a no-op for
rows already at the target (idempotent).

See tbcc/docs/handoffs/2026-08-22_temporary-display-cadence_report.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.models.scheduled_text_post import ScheduledTextPost

LANE_SCHEDULER_NAMES = (
    "ABG / LBFM SCHEDULER",
    "AOF AI SCHEDULER",
    "AOF ASS SCHEDULER",
    "AOF BIG TITS SCHEDULER",
    "AOF BLOWJOB SCHEDULER",
    "AOF BOP SCHEDULER",
    "AOF FULL LENGTH SCHEDULER",
    "AOF GOON SCHEDULER",
    "AOF MILF SCHEDULER",
    "AOF PUBLIC / VOYEUR SCHEDULER",
    "AOF TABOO SCHEDULER",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Write changes (default dry-run)")
    parser.add_argument("--target-minutes", type=int, default=288, help="Target interval_minutes")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = (
            db.query(ScheduledTextPost)
            .filter(ScheduledTextPost.name.in_(LANE_SCHEDULER_NAMES))
            .order_by(ScheduledTextPost.name)
            .all()
        )
        found_names = {r.name for r in rows}
        missing = sorted(set(LANE_SCHEDULER_NAMES) - found_names)
        changed = 0
        for row in rows:
            before = row.interval_minutes
            if before == args.target_minutes:
                print(f"OK    {row.name:<32} pool={row.pool_id} already {before}m")
                continue
            print(f"{'APPLY' if args.execute else 'WOULD-APPLY':<11} {row.name:<32} pool={row.pool_id} {before}m -> {args.target_minutes}m")
            changed += 1
            if args.execute:
                row.interval_minutes = args.target_minutes
        if args.execute and changed:
            db.commit()
        print(f"\n{'Applied' if args.execute else 'Would apply'}: {changed}/{len(rows)} rows changed, {len(rows)}/{len(LANE_SCHEDULER_NAMES)} scheduler names matched.")
        if missing:
            print(f"WARN missing scheduler names (not found in DB): {missing}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
