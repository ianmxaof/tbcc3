"""
Seed click beacons for Reddit promo links (idempotent by slug).

    cd tbcc/backend
    py -3.13 scripts/seed_reddit_beacons.py
    py -3.13 scripts/seed_reddit_beacons.py --execute
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.reddit_beacon_plan import build_reddit_beacon_plan  # noqa: E402
from app.database.session import SessionLocal  # noqa: E402
from app.models.click_link import ClickLink  # noqa: E402
from app.services.click_beacon import create_click_link, public_beacon_base  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Reddit → mainhub click beacons")
    parser.add_argument("--execute", action="store_true", help="write rows (default dry run)")
    parser.add_argument("--only", default="", help="comma-separated subreddit keys")
    args = parser.parse_args()

    plan = build_reddit_beacon_plan()
    only = {k.strip().lower() for k in args.only.split(",") if k.strip()}
    if only:
        plan = [b for b in plan if b.subreddit in only or b.slug in only]
    if not plan:
        print("no beacons matched")
        return 1

    base = public_beacon_base()
    if args.execute and "127.0.0.1" in base:
        print(
            "refusing to seed: TBCC_CLICK_BEACON_PUBLIC_BASE unset "
            "(beacon URLs would be localhost). Set https://api.powercore.app"
        )
        return 2

    db = SessionLocal()
    created = 0
    existing = 0
    try:
        print(f"\nReddit beacons ({'execute' if args.execute else 'dry run'})\n")
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
                    source_ref=b.source_ref,
                )
                created += 1
                status = "created"
            else:
                status = "would create"
            print(f"  r/{b.subreddit}")
            print(f"    beacon   {base}/r/{b.slug}  [{status}]")
            print(f"    dest     {b.destination_url}")
            print(f"    src_ref  {b.source_ref}\n")
    finally:
        db.close()

    print(f"created={created} existing={existing} total={len(plan)}")
    if not args.execute:
        print("dry run — re-run with --execute to write click_links rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
