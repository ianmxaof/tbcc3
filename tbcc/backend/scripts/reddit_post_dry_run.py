"""Seed and inspect Reddit subreddit profiles. Run from tbcc/backend."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.models.reddit_subreddit_profile import RedditSubredditProfile
from app.services.reddit_post_service import fanout_reddit_teaser, plan_post, seed_registry_profiles
from app.services.reddit_rules import check_subreddit_eligibility, pick_eligible_subreddits


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Reddit rules-aware post dry-run / execute")
    p.add_argument("--seed", action="store_true", help="Seed aof_reddit_subreddit_registry into DB")
    p.add_argument("--replace", action="store_true", help="Overwrite registry fields on seed")
    p.add_argument("--list", action="store_true", help="List subreddit profiles")
    p.add_argument("--dry-run", action="store_true", help="Plan post for first eligible sub")
    p.add_argument("--execute", action="store_true", help="Submit (requires TBCC_REDDIT_EXECUTE=1 + API creds)")
    p.add_argument("--enable-scheduled", action="store_true", help="Enable reddit_mirror on buffer-mirror posts")
    p.add_argument("--teaser", default="Teaser drop — rules-safe copy.", help="Title/body hook")
    args = p.parse_args()

    if args.enable_scheduled:
        from app.models.scheduled_text_post import ScheduledTextPost

        with SessionLocal() as db:
            posts = (
                db.query(ScheduledTextPost)
                .filter(ScheduledTextPost.buffer_mirror_enabled.is_(True))
                .order_by(ScheduledTextPost.id.asc())
                .all()
            )
            n = 0
            for post in posts:
                post.reddit_mirror_enabled = True
                n += 1
            if n:
                db.commit()
            print(f"enabled reddit_mirror on {n} scheduled post(s)", file=sys.stderr)

    with SessionLocal() as db:
        if args.seed:
            n = seed_registry_profiles(db, replace=args.replace)
            print(f"seeded {n} profile(s)", file=sys.stderr)

        if args.list or not any((args.seed, args.dry_run, args.execute, args.enable_scheduled)):
            rows = db.query(RedditSubredditProfile).order_by(RedditSubredditProfile.name).all()
            print(json.dumps([{"name": r.name, "status": r.status, "tier": r.tier, "link_policy": r.link_policy} for r in rows], indent=2))

        if args.dry_run or args.execute:
            if args.execute:
                import os

                if (os.getenv("TBCC_REDDIT_EXECUTE") or "0").strip() not in ("1", "true", "yes"):
                    print("ERROR: set TBCC_REDDIT_EXECUTE=1 to submit", file=sys.stderr)
                    return 2
            picks = pick_eligible_subreddits(db, limit=1)
            if not picks:
                print("No eligible subreddit", file=sys.stderr)
                return 1
            prof, el = picks[0]
            plan = plan_post(db, prof, teaser=args.teaser, dry_run=not args.execute)
            if not plan:
                print(f"Plan failed for r/{prof.name}: {el.reason}", file=sys.stderr)
                return 1
            print(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False))
            if args.execute:
                from app.services.reddit_post_service import submit_post

                print(json.dumps(submit_post(db, plan, utm_campaign="manual_dry_run"), indent=2), file=sys.stderr)
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
