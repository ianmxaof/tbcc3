#!/usr/bin/env python3
"""
Loot stock durability preflight — lane depth, survivor refill dry-run, paid-roll smoke steps.

Route #1 ready checklist. Run on island:
  cd /opt/tbcc/backend && python scripts/loot_durability_check.py
  python scripts/loot_durability_check.py --apply-refill --unpause   # operator: recycle survivors

Paid-roll smoke (operator sandbox — unlimited pulls):
  DM @aof_lootgod_bot → /roll (or key checkout path). Expect album DM delivery.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.session import SessionLocal
from app.services.lane_survivor_refill import refill_lanes_from_survivors_sync
from app.services.operator_sandbox import operator_sandbox_ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Loot durability preflight")
    parser.add_argument("--target", type=int, default=60, help="approved depth target per lane")
    parser.add_argument("--probe-cap", type=int, default=120)
    parser.add_argument("--apply-refill", action="store_true", help="execute survivor refill")
    parser.add_argument("--unpause", action="store_true", help="clear auto-pause on refilled lanes")
    args = parser.parse_args()

    with SessionLocal() as db:
        report = refill_lanes_from_survivors_sync(
            db,
            target=args.target,
            probe_cap=args.probe_cap,
            execute=args.apply_refill,
            unpause=args.unpause,
        )

    print("=== Loot durability check ===\n")
    print(f"probed Saved Message refs: {report.get('probed', 0)}")
    print(f"{'lane':<12} {'approved':>8} {'need':>5} {'local':>6} {'alive':>6} {'restore':>8}")
    for key, row in sorted((report.get("lanes") or {}).items()):
        need = int(row.get("need") or 0)
        if need <= 0:
            print(f"{key:<12} {row.get('approved', 0):>8} {0:>5} {'-':>6} {'-':>6} {'ok':>8}")
            continue
        print(
            f"{key:<12} {row.get('approved', 0):>8} {need:>5} "
            f"{row.get('local', 0):>6} {row.get('alive', 0):>6} {row.get('restore', 0):>8}"
        )

    total = report.get("restored_total") if args.apply_refill else report.get("would_restore")
    print(f"\ntotal rows {'restored' if args.apply_refill else 'would restore'}: {total}")
    if not args.apply_refill and int(total or 0) > 0:
        print("→ run with --apply-refill to recycle survivors (still not fresh imports)")

    print("\n=== Operator paid-roll smoke (sandbox ids) ===")
    print(f"  operator_ids: {sorted(operator_sandbox_ids())}")
    print("  1. DM @aof_lootgod_bot — /roll (free) or buy loot key via @aofsubscriptions_bot")
    print("  2. Expect album in DM; check celery loot delivery logs if empty")
    print("  3. Fresh stock: Storage Hub deposits + local imports (TBCC_LOOT_LOCAL_BYTES_ONLY=1)")

  return 0


if __name__ == "__main__":
    raise SystemExit(main())
