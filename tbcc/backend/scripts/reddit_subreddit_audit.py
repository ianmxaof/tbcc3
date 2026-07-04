"""Fetch subreddit rules via Reddit API and store in reddit_subreddit_profiles."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Audit subreddit rules (PRAW)")
    p.add_argument("subreddits", nargs="*", help="r/name or name")
    p.add_argument("--save", action="store_true", help="Persist rules_snippet to DB")
    args = p.parse_args()

    from app.database.session import SessionLocal
    from app.models.reddit_subreddit_profile import RedditSubredditProfile
    from app.services.reddit_post_service import _reddit_client
    from app.services.reddit_rules import normalize_subreddit_name

    names = [normalize_subreddit_name(s) for s in args.subreddits if s.strip()]
    if not names:
        print("Provide at least one subreddit name", file=sys.stderr)
        return 2

    reddit = _reddit_client()
    db = SessionLocal()
    try:
        for name in names:
            sub = reddit.subreddit(name)
            rules = []
            try:
                for rule in sub.rules:
                    rules.append({"short_name": rule.short_name, "description": rule.description})
            except Exception as e:
                rules = [{"error": str(e)}]
            snippet = "\n".join(
                f"- {r.get('short_name', '?')}: {(r.get('description') or '')[:200]}" for r in rules[:15]
            )
            out = {
                "name": name,
                "subscribers": getattr(sub, "subscribers", None),
                "over18": getattr(sub, "over18", None),
                "rules_count": len(rules),
                "rules_snippet": snippet[:4000],
            }
            print(json.dumps(out, indent=2, ensure_ascii=False))
            if args.save:
                row = db.query(RedditSubredditProfile).filter(RedditSubredditProfile.name == name).first()
                if row is None:
                    row = RedditSubredditProfile(name=name, status="probation")
                    db.add(row)
                row.rules_snippet = snippet[:8000] or None
                row.rules_json = json.dumps(rules)[:12000]
                row.rules_fetched_at = datetime.utcnow()
                row.updated_at = datetime.utcnow()
        if args.save:
            db.commit()
            print("saved", file=sys.stderr)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
