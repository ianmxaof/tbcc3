"""
Smoke: every seeded beacon resolves to something the loot bot can answer.

Run on the island after seeding beacons:
    docker compose ... exec -T api python scripts/smoke_lane_gate_relay.py --week wk31
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.gate_beacon_plan import ATTRIBUTION_FULL, build_gate_beacon_plan  # noqa: E402
from app.database.session import SessionLocal  # noqa: E402
from app.models.click_link import ClickLink  # noqa: E402
from app.services.lane_gate_relay import lane_invite_url, parse_lane_gate_payload  # noqa: E402
from app.services.traffic_attribution import payload_to_source_ref  # noqa: E402

BOT_ROUTE_KEYS = {"loot", "main_group", "lootgod"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke seeded gate beacons")
    parser.add_argument("--week", required=True)
    args = parser.parse_args()

    plan = build_gate_beacon_plan(args.week)
    db = SessionLocal()
    failures: list[str] = []
    try:
        for b in plan:
            link = db.query(ClickLink).filter(ClickLink.slug == b.slug).first()
            if not link:
                failures.append(f"{b.key}: beacon {b.slug} missing — run seed_gate_beacons.py --execute")
                continue
            if (link.source_ref or "") != b.source_ref:
                failures.append(
                    f"{b.key}: beacon source_ref {link.source_ref!r} != plan {b.source_ref!r}"
                )
            if link.destination_url != b.destination_url:
                failures.append(f"{b.key}: destination drifted from plan ({link.destination_url})")
            if payload_to_source_ref(b.source_ref) != b.source_ref:
                failures.append(f"{b.key}: source_ref does not round-trip through attribution")

            if b.attribution == ATTRIBUTION_FULL and b.key not in BOT_ROUTE_KEYS:
                parsed = parse_lane_gate_payload(b.source_ref)
                if not parsed:
                    failures.append(f"{b.key}: bot cannot parse {b.source_ref} — traffic would dead-end")
                elif not lane_invite_url(parsed[0]):
                    failures.append(f"{b.key}: lane {parsed[0]} has no invite to hand over")

            status = "OK " if not failures or not failures[-1].startswith(f"{b.key}:") else "BAD"
            print(f"  {status} {b.key.ljust(11)} {b.attribution.ljust(10)} -> {link.destination_url}")
    finally:
        db.close()

    print()
    if failures:
        print(f"FAIL — {len(failures)} problem(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"PASS — {len(plan)} beacons seeded, resolvable, and round-tripping.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
