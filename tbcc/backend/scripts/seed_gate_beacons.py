"""
Create one click beacon per Linkvertise gate destination (idempotent by slug).

Dry run (default) prints the operator paste table; --execute writes click_links.

    cd tbcc/backend
    py -3.13 scripts/seed_gate_beacons.py --week wk31
    py -3.13 scripts/seed_gate_beacons.py --week wk31 --execute

After executing, paste each Beacon URL into the matching Linkvertise slug's
destination field. Lane gates are click-only until a lane-invite start handler
exists on the loot bot; bot gates close the full click -> conversion loop.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.gate_beacon_plan import build_gate_beacon_plan  # noqa: E402
from app.database.session import SessionLocal  # noqa: E402
from app.models.click_link import ClickLink  # noqa: E402
from app.services.click_beacon import create_click_link, public_beacon_base  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Linkvertise gate click beacons")
    parser.add_argument("--week", required=True, help="campaign week tag, e.g. wk31")
    parser.add_argument("--execute", action="store_true", help="write rows (default dry run)")
    parser.add_argument("--only", default="", help="comma-separated gate keys to limit to")
    args = parser.parse_args()

    try:
        plan = build_gate_beacon_plan(args.week)
    except ValueError as e:
        print(f"error: {e}")
        return 2

    only = {k.strip().lower() for k in args.only.split(",") if k.strip()}
    if only:
        plan = [b for b in plan if b.key in only]
    if not plan:
        print("no gate keys matched")
        return 1

    base = public_beacon_base()
    if args.execute and "127.0.0.1" in base:
        print(
            "refusing to seed: TBCC_CLICK_BEACON_PUBLIC_BASE is unset "
            "(beacon URLs would be localhost). Set it to https://api.powercore.app first."
        )
        return 2

    db = SessionLocal()
    created = 0
    existing = 0
    rows: list[tuple[str, str, str, str, str]] = []
    try:
        for b in plan:
            found = db.query(ClickLink).filter(ClickLink.slug == b.slug).first()
            if found:
                existing += 1
                status = "exists"
            elif args.execute:
                create_click_link(
                    db,
                    destination_url=b.destination_url,
                    label=b.label,
                    slug=b.slug,
                    # Stamped even for click_only lanes so the funnel report can
                    # show clicks that never became a touch.
                    source_ref=b.source_ref,
                )
                created += 1
                status = "created"
            else:
                status = "would create"
            rows.append((b.key, f"{base}/r/{b.slug}", b.gate_url, b.attribution, status))
    finally:
        db.close()

    width = max(len(r[0]) for r in rows)
    print(f"\nGate beacons — week {args.week} ({'execute' if args.execute else 'dry run'})\n")
    for key, beacon_url, gate_url, attribution, status in rows:
        print(f"  {key.ljust(width)}  {beacon_url}")
        print(f"  {' '.ljust(width)}  paste into: {gate_url}")
        print(f"  {' '.ljust(width)}  attribution: {attribution}  [{status}]\n")

    print(f"created={created} existing={existing} total={len(rows)}")
    if not args.execute:
        print("dry run — re-run with --execute to write click_links rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
