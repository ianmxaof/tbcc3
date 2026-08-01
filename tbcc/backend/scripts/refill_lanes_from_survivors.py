"""Top up thin lane pools from media that is still deliverable.

Generalizes refill_ai_lane_from_survivors across the whole AOF network. For each content
lane below the depth target, recover rotation stock from two sources that can actually be
sent today:

1. Local-disk rows (`local:` file ids) — bytes live on the volume, never go stale.
2. Previously posted rows whose Saved Message reference still resolves.

Everything recovered is recycled content. This restores cadence on starved lanes; it does
not replace fresh deposits into the Storage Hub topics.
"""

from __future__ import annotations

import argparse
import sys

from app.database.session import SessionLocal
from app.services.lane_survivor_refill import refill_lanes_from_survivors_sync


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--target", type=int, default=60, help="desired approved depth per lane")
    parser.add_argument("--probe-cap", type=int, default=120, help="max posted rows probed per lane")
    parser.add_argument("--unpause", action="store_true", help="clear auto-pause on refilled lanes")
    args = parser.parse_args()

    with SessionLocal() as db:
        report = refill_lanes_from_survivors_sync(
            db,
            target=args.target,
            probe_cap=args.probe_cap,
            execute=args.apply,
            unpause=args.unpause,
        )

    print(f"probing {report.get('probed', 0)} Saved Message refs across thin lanes...\n")
    print(f"{'lane':<12} {'approved':>8} {'need':>5} {'local':>6} {'alive':>6} {'restore':>8}")
    for key, row in (report.get("lanes") or {}).items():
        need = int(row.get("need") or 0)
        if need <= 0:
            print(f"{key:<12} {row.get('approved', 0):>8} {0:>5} {'-':>6} {'-':>6} {'ok':>8}")
            continue
        print(
            f"{key:<12} {row.get('approved', 0):>8} {need:>5} "
            f"{row.get('local', 0):>6} {row.get('alive', 0):>6} {row.get('restore', 0):>8}"
        )

    total = report.get("restored_total") if args.apply else report.get("would_restore")
    print(f"\ntotal rows that would return to rotation: {total}")
    if not args.apply:
        print("(dry run — pass --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
