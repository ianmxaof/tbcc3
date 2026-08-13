#!/usr/bin/env python3
"""
Resync AOF lane schedulers + the PACKS scheduler onto the expanded flavor-hook banks
built in Phases 1-3 of the flavor caption resupply. See
tbcc/docs/handoffs/2026-08-13_aof-flavor-caption-resupply_phase{1,2,3}_report.md.

--dry-run (default): read-only. Calls sync_network_schedulers(db, execute=False), which
  computes but never persists each lane's variations_before_dedupe / variations /
  unique_hooks (see aof_growth_hub.sync_network_schedulers). For PACKS, compares the
  live scheduler's current content_variations count against the size of
  pack_caption_template_variations() without calling the mutating
  refresh_aof_packs_scheduler(). No DB writes either way; the session is rolled back.

--execute: calls sync_network_schedulers(db, execute=True) and
  refresh_aof_packs_scheduler(db) for real, commits, and prints the same before/after
  numbers measured from the actual writes.

Usage:
    cd tbcc/backend
    py -3.13 scripts/resync_flavor_captions.py --dry-run
    py -3.13 scripts/resync_flavor_captions.py --execute
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv  # noqa: E402

load_tbcc_dotenv()

from app.database.session import SessionLocal  # noqa: E402


def _lane_report(db, *, execute: bool) -> list[dict[str, Any]]:
    from app.services.aof_growth_hub import sync_network_schedulers

    report = sync_network_schedulers(db, execute=execute)
    rows: list[dict[str, Any]] = []
    for entry in report.get("channels", []):
        if "unique_hooks" not in entry:
            # bulletin/other non-lane rows (e.g. pinned_bulletin) don't carry these fields
            continue
        rows.append(
            {
                "key": entry.get("key"),
                "status": entry.get("status"),
                "variations_before_dedupe": entry.get("variations_before_dedupe"),
                "variations": entry.get("variations"),
                "unique_hooks": entry.get("unique_hooks"),
            }
        )
    return rows


def _packs_report(db, *, execute: bool) -> dict[str, Any]:
    from app.models.scheduled_text_post import ScheduledTextPost
    from app.services.aof_packs_caption_templates import pack_caption_template_variations
    from app.services.loot_pack_pool import SCHED_NAME

    bank_size = len(pack_caption_template_variations())
    sched = db.query(ScheduledTextPost).filter(ScheduledTextPost.name == SCHED_NAME).first()
    live_before = 0
    if sched:
        vars_ = sched.get_content_variations() or ([sched.content] if sched.content else [])
        live_before = len(vars_)

    result: dict[str, Any] = {
        "scheduler_found": bool(sched),
        "bank_size": bank_size,
        "live_before": live_before,
    }
    if execute:
        from app.services.loot_pack_pool import refresh_aof_packs_scheduler

        refresh_result = refresh_aof_packs_scheduler(db)
        result["refresh_result"] = refresh_result
        result["live_after"] = refresh_result.get("caption_template_count")
    else:
        result["would_change"] = live_before != bank_size
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read-only (default behavior even without this flag; accepted explicitly for clarity in docs/CI)",
    )
    parser.add_argument("--execute", action="store_true", help="Write changes (overrides --dry-run if both are passed)")
    args = parser.parse_args()
    execute = bool(args.execute)

    db = SessionLocal()
    try:
        lane_rows = _lane_report(db, execute=execute)
        packs = _packs_report(db, execute=execute)
        if execute:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()

    print(f"=== AOF flavor caption resync -- {'EXECUTE' if execute else 'DRY RUN'} ===\n")
    print("-- Lane schedulers --")
    if not lane_rows:
        print("  (no lane rows returned -- channels/schedulers not found in this DB)")
    for row in lane_rows:
        key = str(row["key"])
        status = str(row["status"])
        print(
            f"  {key:<14} status={status:<16} "
            f"before_dedupe={row['variations_before_dedupe']!s:<5} "
            f"after={row['variations']!s:<5} unique_hooks={row['unique_hooks']}"
        )

    print("\n-- PACKS scheduler --")
    print(f"  scheduler_found={packs['scheduler_found']}")
    print(f"  bank_size (pack_caption_template_variations)={packs['bank_size']}")
    print(f"  live_before={packs['live_before']}")
    if execute:
        print(f"  live_after={packs.get('live_after')}")
    else:
        print(f"  would_change={packs.get('would_change')}")

    if not execute:
        print("\nDry run only -- no DB writes were committed. Re-run with --execute to apply.")
    else:
        print("\nExecuted -- changes committed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
