#!/usr/bin/env python3
"""
Backfill: queue approved master-archive pack candidates into AOF packs pool.

Usage:
  cd tbcc/backend
  py -3.13 scripts/archive_pack_autopilot_backfill.py
  py -3.13 scripts/archive_pack_autopilot_backfill.py --execute --wire-scheduler
  py -3.13 scripts/archive_pack_autopilot_backfill.py --execute --limit 20
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
from app.models.capture_archive_entry import CaptureArchiveEntry
from app.services.archive_pack_autopilot import (
    archive_auto_pack_queue_enabled,
    try_auto_queue_archive_entry_to_pack_pool,
)
from app.services.loot_pack_pool import is_pack_candidate_url, pack_pool_modifier_exists


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="Backfill archive → AOF packs pool autopilot")
    p.add_argument("--execute", action="store_true", help="Queue modifiers (default dry-run)")
    p.add_argument("--limit", type=int, default=0, help="Max rows to process (0 = all)")
    p.add_argument("--wire-scheduler", action="store_true", help="Refresh AOF PACKS scheduler after queue")
    args = p.parse_args()

    if not archive_auto_pack_queue_enabled():
        print("TBCC_ARCHIVE_AUTO_PACK_QUEUE is off — pass --execute only after enabling.", file=sys.stderr)

    db = SessionLocal()
    queued = dup = skipped = fail = would = 0
    try:
        rows = (
            db.query(CaptureArchiveEntry)
            .filter(CaptureArchiveEntry.kind == "url", CaptureArchiveEntry.status == "approved")
            .order_by(CaptureArchiveEntry.added_at.desc())
            .all()
        )
        if args.limit > 0:
            rows = rows[: args.limit]

        for row in rows:
            url = (row.value or "").strip()
            if not is_pack_candidate_url(url):
                continue
            if pack_pool_modifier_exists(db, url, url):
                dup += 1
                continue
            if not args.execute:
                would += 1
                print(f"DRY id={row.id} {url[:90]}")
                continue
            result = try_auto_queue_archive_entry_to_pack_pool(
                db,
                row,
                enabled=True,
                wire_scheduler=False,
            )
            if not result:
                continue
            if result.get("skipped"):
                skipped += 1
                print(f"SKIP id={row.id} {result.get('reason')}")
            elif result.get("duplicate"):
                dup += 1
            elif result.get("created"):
                queued += 1
                mod = result.get("modifier") or {}
                print(f"OK id={row.id} mod={mod.get('id')} {(url)[:80]}")
            else:
                fail += 1
                print(f"FAIL id={row.id} {result.get('error')}")

        if args.execute and args.wire_scheduler and queued > 0:
            from app.services.loot_pack_pool import refresh_aof_packs_scheduler

            sched = refresh_aof_packs_scheduler(db)
            print(f"SCHEDULER ok={sched.get('ok')} modifiers={sched.get('modifier_count')}")
    finally:
        db.close()

    mode = "execute" if args.execute else "dry-run"
    print(f"\n--- {mode}: would={would} queued={queued} dup={dup} skipped={skipped} fail={fail}")


if __name__ == "__main__":
    main()
