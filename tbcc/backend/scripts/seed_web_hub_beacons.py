"""
Seed click beacons for AOF Hub web CTAs (idempotent by slug).

    cd tbcc/backend
    py -3.13 scripts/seed_web_hub_beacons.py
    py -3.13 scripts/seed_web_hub_beacons.py --execute

Operator: after Awempire approval, update web-live-* destination_url rows
(or re-run with AWEMPIRE_OUTBOUND_URL_GIRLS / AWEMPIRE_OUTBOUND_URL_COUPLES env).
Same for web-vpapi-* rows via AWEMPIRE_VPAPI_OUTBOUND_URL (applies to all
labels uniformly — no per-category links available yet, see P9 phase 2 report).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.web_hub_beacon_plan import WebHubBeacon, build_web_hub_beacon_plan  # noqa: E402
from app.database.session import SessionLocal  # noqa: E402
from app.models.click_link import ClickLink  # noqa: E402
from app.services.click_beacon import create_click_link, public_beacon_base  # noqa: E402


def _apply_awempire_overrides(plan: list[WebHubBeacon]) -> list[WebHubBeacon]:
    girls = (os.getenv("AWEMPIRE_OUTBOUND_URL_GIRLS") or "").strip()
    couples = (os.getenv("AWEMPIRE_OUTBOUND_URL_COUPLES") or "").strip()
    vpapi = (os.getenv("AWEMPIRE_VPAPI_OUTBOUND_URL") or "").strip()
    out: list[WebHubBeacon] = []
    for b in plan:
        if b.slug == "web-live-girls" and girls:
            out.append(
                WebHubBeacon(b.slug, b.label, girls, b.source_ref)
            )
        elif b.slug == "web-live-couples" and couples:
            out.append(
                WebHubBeacon(b.slug, b.label, couples, b.source_ref)
            )
        elif b.slug.startswith("web-vpapi-") and vpapi:
            out.append(
                WebHubBeacon(b.slug, b.label, vpapi, b.source_ref)
            )
        else:
            out.append(b)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed AOF Hub web click beacons")
    parser.add_argument("--execute", action="store_true", help="write rows (default dry run)")
    parser.add_argument("--only", default="", help="comma-separated slugs")
    args = parser.parse_args()

    plan = _apply_awempire_overrides(build_web_hub_beacon_plan())
    only = {k.strip().lower() for k in args.only.split(",") if k.strip()}
    if only:
        plan = [b for b in plan if b.slug in only]
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
    updated = 0
    existing = 0
    try:
        print(f"\nWeb hub beacons ({'execute' if args.execute else 'dry run'})\n")
        for b in plan:
            found = db.query(ClickLink).filter(ClickLink.slug == b.slug).first()
            if found:
                existing += 1
                status = "exists"
                if args.execute and found.destination_url != b.destination_url:
                    found.destination_url = b.destination_url
                    if not found.source_ref:
                        found.source_ref = b.source_ref
                    db.commit()
                    updated += 1
                    status = "updated"
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
            print(f"  {b.slug} [{status}]")
            print(f"    beacon   {base}/r/{b.slug}")
            print(f"    dest     {b.destination_url}")
            print(f"    src_ref  {b.source_ref}\n")
    finally:
        db.close()

    print(f"created={created} updated={updated} existing={existing} total={len(plan)}")
    if not args.execute:
        print("dry run — re-run with --execute to write click_links rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
