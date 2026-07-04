#!/usr/bin/env python3
"""
Read-only audit of scheduled_text_posts rows — report only, no deletes.

Usage:
  cd tbcc/backend
  py -3.13 scripts/audit_scheduler_rows.py
  py -3.13 scripts/audit_scheduler_rows.py --stale-days 30 --sent-one-shot-days 90
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.scheduler_category import infer_scheduler_category


def _parse_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return None


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="Audit scheduled_text_posts (read-only)")
    p.add_argument("--stale-days", type=int, default=30, help="Recurring with no last_posted_at this long")
    p.add_argument(
        "--sent-one-shot-days",
        type=int,
        default=90,
        help="Sent one-shots older than N days (candidates for hide-sent filter)",
    )
    args = p.parse_args()

    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=max(1, args.stale_days))
    sent_cutoff = now - timedelta(days=max(1, args.sent_one_shot_days))

    db = SessionLocal()
    try:
        rows = db.query(ScheduledTextPost).order_by(ScheduledTextPost.id.asc()).all()
        name_counts: Counter[str] = Counter()
        by_category: Counter[str] = Counter()
        stale_recurring: list[dict] = []
        duplicate_names: dict[str, list[int]] = defaultdict(list)
        old_sent_one_shots: list[dict] = []

        for row in rows:
            name = (row.name or "").strip() or f"(id {row.id})"
            name_counts[name] += 1
            duplicate_names[name].append(int(row.id))
            cat = infer_scheduler_category(row.name, row.scheduler_category)
            by_category[cat] += 1

            recurring = bool(row.interval_minutes and int(row.interval_minutes) > 0)
            if recurring:
                last = _parse_dt(row.last_posted_at)
                if last is None or last < stale_cutoff:
                    stale_recurring.append(
                        {
                            "id": row.id,
                            "name": name,
                            "interval_minutes": row.interval_minutes,
                            "last_posted_at": last.isoformat() if last else None,
                            "category": cat,
                        }
                    )
            elif row.sent_at:
                sent = _parse_dt(row.sent_at)
                if sent and sent < sent_cutoff:
                    old_sent_one_shots.append(
                        {
                            "id": row.id,
                            "name": name,
                            "sent_at": sent.isoformat(),
                            "category": cat,
                        }
                    )

        dupes = {n: ids for n, ids in duplicate_names.items() if len(ids) > 1}

        print(f"Scheduled posts audit ({len(rows)} rows)")
        print(f"  by category: {dict(sorted(by_category.items()))}")
        print(f"  recurring stale (no post in {args.stale_days}d): {len(stale_recurring)}")
        print(f"  duplicate names: {len(dupes)}")
        print(f"  old sent one-shots (>{args.sent_one_shot_days}d): {len(old_sent_one_shots)}")

        if stale_recurring:
            print("\n--- Stale recurring (sample up to 20) ---")
            for entry in stale_recurring[:20]:
                print(f"  #{entry['id']} {entry['name']} last={entry['last_posted_at']}")

        if dupes:
            print("\n--- Duplicate names ---")
            for name, ids in sorted(dupes.items(), key=lambda x: -len(x[1]))[:20]:
                print(f"  {name!r}: ids={ids}")

        if old_sent_one_shots:
            print("\n--- Old sent one-shots (sample up to 20) ---")
            for entry in old_sent_one_shots[:20]:
                print(f"  #{entry['id']} {entry['name']} sent={entry['sent_at']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
