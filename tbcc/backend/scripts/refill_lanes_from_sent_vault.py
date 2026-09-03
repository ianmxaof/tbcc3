"""Dry lane pools → recycle stamped items from SENT VAULT (emoji / #tbcc:lane)."""

from __future__ import annotations

import argparse
import sys

from app.database.session import SessionLocal
from app.services.sent_vault_lane_refill import refill_dry_lanes_from_sent_vault_sync


def main() -> int:
    parser = argparse.ArgumentParser(description="Refill dry AOF lanes from SENT VAULT archive")
    parser.add_argument("--apply", action="store_true", help="execute (default dry-run)")
    parser.add_argument("--target", type=int, default=None, help="desired approved depth per lane")
    parser.add_argument("--min-approved", type=int, default=None, help="refill when below this count")
    parser.add_argument("--unpause", action="store_true", help="clear auto-pause on refilled schedulers")
    args = parser.parse_args()

    with SessionLocal() as db:
        report = refill_dry_lanes_from_sent_vault_sync(
            db,
            target=args.target,
            min_approved=args.min_approved,
            execute=args.apply,
            unpause=args.unpause,
        )

    print(f"skipped lanes: {', '.join(report.get('skipped_keys') or [])}\n")
    print(f"{'lane':<12} {'approved':>8} {'need':>5}  stamp")
    for key, row in (report.get("lanes") or {}).items():
        need = int(row.get("need") or 0)
        if need <= 0:
            continue
        print(
            f"{key:<12} {row.get('approved', 0):>8} {need:>5}  {row.get('stamp', '')}"
        )

    total = report.get("restored_total") if args.apply else report.get("would_restore")
    print(f"\ntotal rows {'restored' if args.apply else 'that would restore'}: {total}")
    if not args.apply:
        print("(dry run — pass --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
