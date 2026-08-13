"""
Reddit circuit go-live helper — seed registry, beacons, dry-run plan, env checklist.

Erome lane excluded (operator IP ban). First live sub: r/DailyTelegram.

    cd tbcc/backend
    py -3.13 scripts/reddit_go_live.py
    py -3.13 scripts/reddit_go_live.py --execute-beacons
    py -3.13 scripts/reddit_go_live.py --dry-run-post
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()


def _env_checklist() -> list[tuple[str, str, bool]]:
    keys = (
        "TBCC_REDDIT_CLIENT_ID",
        "TBCC_REDDIT_CLIENT_SECRET",
        "TBCC_REDDIT_USERNAME",
        "TBCC_REDDIT_PASSWORD",
        "TBCC_REDDIT_USER_AGENT",
        "TBCC_CLICK_BEACON_PUBLIC_BASE",
    )
    flags = (
        ("TBCC_REDDIT_ENABLED", "1"),
        ("TBCC_REDDIT_EXECUTE", "0 for dry-run / 1 for live"),
        ("TBCC_REDDIT_MIRROR_ON_SCHEDULED", "1"),
        ("TBCC_REDDIT_USE_BEACON", "1"),
        ("TBCC_REDDIT_GLOBAL_MAX_POSTS_PER_DAY", "2-3"),
        ("TBCC_REDDIT_GLOBAL_MIN_GAP_HOURS", "4-6"),
    )
    rows: list[tuple[str, str, bool]] = []
    for k in keys:
        v = (os.getenv(k) or "").strip()
        rows.append((k, v[:40] + ("…" if len(v) > 40 else ""), bool(v)))
    for k, hint in flags:
        v = (os.getenv(k) or "").strip()
        rows.append((k, v or f"(unset — want {hint})", bool(v)))
    return rows


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="Reddit promo go-live checklist")
    p.add_argument("--seed", action="store_true", help="Seed subreddit registry into DB")
    p.add_argument("--replace", action="store_true", help="Overwrite registry fields on seed")
    p.add_argument("--execute-beacons", action="store_true", help="Seed reddit click beacons")
    p.add_argument("--enable-mirrors", action="store_true", help="Enable reddit_mirror on VIP/Loot schedulers")
    p.add_argument("--dry-run-post", action="store_true", help="Plan post for first eligible sub")
    p.add_argument("--teaser", default="AOF curated Telegram network — lanes, loot, VIP skip.")
    args = p.parse_args()

    print("=== Reddit go-live checklist (Erome out) ===\n")
    for key, val, ok in _env_checklist():
        mark = "ok" if ok else "MISSING"
        print(f"  [{mark}] {key}: {val or '(empty)'}")

    print("\nOperator steps:")
    print("  1. Reddit app creds + dedicated account (5+ mo ideal)")
    print("  2. py scripts/reddit_subreddit_audit.py telegramNSFW1818 --save")
    print("  3. TBCC_REDDIT_ENABLED=1, EXECUTE=0 → dry-run → EXECUTE=1 for telegramNSFW1818 only")
    print("  4. py scripts/seed_reddit_beacons.py --execute")
    print("  5. py scripts/enable_vip_platform_mirrors.py --execute")
    print("  6. Post Telegram Story within 60m of each Reddit hit (see docs/REDDIT_STORIES_PROMO_PLAYBOOK.md)")

    if args.seed or args.replace:
        from app.database.session import SessionLocal
        from app.services.reddit_post_service import seed_registry_profiles

        try:
            with SessionLocal() as db:
                n = seed_registry_profiles(db, replace=args.replace)
                print(f"\nseeded {n} subreddit profile(s)")
        except Exception as e:
            print(f"\nWARN: seed skipped — DB unavailable: {e}")
            if args.seed:
                return 2

    if args.execute_beacons:
        from app.data.reddit_beacon_plan import build_reddit_beacon_plan
        from app.database.session import SessionLocal
        from app.models.click_link import ClickLink
        from app.services.click_beacon import create_click_link, public_beacon_base

        base = public_beacon_base()
        if "127.0.0.1" in base:
            print("\nERROR: set TBCC_CLICK_BEACON_PUBLIC_BASE before --execute-beacons")
            return 2
        db = SessionLocal()
        created = 0
        try:
            for b in build_reddit_beacon_plan():
                if db.query(ClickLink).filter(ClickLink.slug == b.slug).first():
                    continue
                create_click_link(
                    db,
                    destination_url=b.destination_url,
                    label=b.label,
                    slug=b.slug,
                    source_ref=b.source_ref,
                )
                created += 1
            print(f"\nreddit beacons created={created}")
        finally:
            db.close()

    if args.enable_mirrors:
        from scripts.enable_vip_platform_mirrors import apply

        print(json.dumps(apply(execute=True), indent=2))

    if args.dry_run_post:
        from app.database.session import SessionLocal
        from app.services.reddit_post_service import plan_post, seed_registry_profiles
        from app.services.reddit_rules import pick_eligible_subreddits

        try:
            with SessionLocal() as db:
                seed_registry_profiles(db, replace=False)
                picks = pick_eligible_subreddits(db, limit=1)
                if not picks:
                    print("\nNo eligible subreddit — check registry status/cooldowns")
                    return 1
                prof, el = picks[0]
                plan = plan_post(db, prof, teaser=args.teaser, dry_run=True)
                if not plan:
                    print(f"\nPlan failed for r/{prof.name}: {el.reason}")
                    return 1
                print("\n--- dry-run plan ---")
                print(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"\nWARN: dry-run post skipped — DB unavailable: {e}")
            return 2

    if not any(
        (
            args.seed,
            args.replace,
            args.execute_beacons,
            args.enable_mirrors,
            args.dry_run_post,
        )
    ):
        print("\nTip: --seed --execute-beacons --enable-mirrors --dry-run-post")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
