#!/usr/bin/env python3
"""Retarget canonical AOF Linkvertise gate posts to wkNN beacon URLs (Playwright).

You do NOT need to hand-edit 15 LV rows. This uses the same Brave session as pack provisioning.

    cd tbcc/backend
    py -3.13 scripts/retarget_lv_gate_beacons.py --week wk31 --dry-run
    py -3.13 scripts/retarget_lv_gate_beacons.py --week wk31 --execute --headed
    py -3.13 scripts/retarget_lv_gate_beacons.py --week wk31 --execute --limit 3

Auth: backend/.linkvertise-auth.json (or TBCC_BRAVE_PROFILE_NAME persistent profile).
Flow: app/data/linkvertise_dashboard_flow.local.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.services.linkvertise_dashboard_provision import (
    auth_state_path,
    flow_config_path,
    load_flow_config,
    retarget_gate_beacons_for_week,
    selectors_ready,
)
from app.services.playwright_browser import browser_label, describe_launch_mode, use_brave_persistent_profile


def main() -> int:
    p = argparse.ArgumentParser(description="Retarget AOF manual LV gates to beacon URLs")
    p.add_argument("--week", default="", help="Campaign week tag, e.g. wk31")
    p.add_argument("--dry-run", action="store_true", help="Print gate_url -> beacon_url only")
    p.add_argument("--execute", action="store_true", help="Run Playwright retarget on LV dashboard")
    p.add_argument("--headed", action="store_true", help="Show browser (recommended first run)")
    p.add_argument("--limit", type=int, default=None, help="Max gates this run")
    p.add_argument("--only", default="", help="Comma-separated gate keys (ass,loot,...)")
    p.add_argument(
        "--beacon-base",
        default="https://api.powercore.app",
        help="Beacon host base (default https://api.powercore.app)",
    )
    p.add_argument("--refresh-login", action="store_true", help="Re-export LV cookies (--login) before execute")
    p.add_argument("--record-retarget", action="store_true", help="Open posts list + Inspector to record Edit flow")
    args = p.parse_args()

    if args.record_retarget:
        from app.services.linkvertise_dashboard_provision import record_retarget_flow

        record_retarget_flow(headed=True)
        return 0

    if args.refresh_login:
        from app.services.linkvertise_dashboard_provision import login_and_save_session

        print("Opening Linkvertise login — confirm dashboard in browser, then Resume in Inspector.\n")
        login_and_save_session(headed=True)
        return 0

    if not (args.week or "").strip():
        p.error("--week is required for --dry-run / --execute")

    keys = [k.strip() for k in args.only.split(",") if k.strip()] or None

    if args.dry_run:
        rows = retarget_gate_beacons_for_week(
            args.week,
            dry_run=True,
            keys=keys,
            beacon_base=args.beacon_base,
            limit=args.limit,
        )
        print(f"\nRetarget plan — week {args.week} (dry run)\n")
        for row in rows:
            if row.get("skip"):
                print(f"  SKIP {row['key']:12}  {row.get('reason')}  {row.get('gate_url', '')}")
            else:
                print(f"  {row['key']:12}  {row['gate_url']}")
                print(f"  {'':12}  -> {row['beacon_url']}")
        print(f"\nTotal: {len(rows)}")
        return 0

    if not args.execute:
        p.print_help()
        return 0

    cfg = load_flow_config()
    auth = auth_state_path()
    print(f"Browser:     {browser_label()}")
    print(f"Flow config: {flow_config_path()}")
    print(f"Auth:        {auth} ({'ok' if auth.is_file() or use_brave_persistent_profile() else 'MISSING'})")
    print(f"Launch:      {describe_launch_mode(storage_state=auth)}")
    print(f"Selectors:   {selectors_ready(cfg)}")
    if not selectors_ready(cfg):
        print("ERROR: destination_input / submit_button missing in flow config.", file=sys.stderr)
        return 2

    print(f"\nRetargeting week {args.week} via Playwright…\n")
    results = retarget_gate_beacons_for_week(
        args.week,
        headed=args.headed,
        keys=keys,
        beacon_base=args.beacon_base,
        limit=args.limit,
    )
    ok = sum(1 for r in results if r.get("ok"))
    skip = sum(1 for r in results if r.get("skip"))
    fail = len(results) - ok - skip
    for row in results:
        key = row.get("key", "?")
        if row.get("skip"):
            print(f"  SKIP {key}: {row.get('reason')}")
        elif row.get("ok"):
            print(f"  OK   {key}: {row.get('gate_url')} -> {row.get('beacon_destination', row.get('beacon_url'))}")
        else:
            print(f"  FAIL {key}: {row.get('error', row)}")
    print(f"\nDone: ok={ok} skip={skip} fail={fail} total={len(results)}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
