"""Dry-run or force weekly build log (PATCH NOTES + @aofmainhub). Run from tbcc/backend."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.services.build_log_draft import (
    collect_weekly_build_log_context,
    draft_mainhub_snippet_html,
    draft_patch_notes_html,
    extract_build_log_items,
)
from app.services.weekly_build_log import _iso_week_key, queue_weekly_build_log_posts
from datetime import datetime, timezone


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="TBCC weekly build log — PATCH NOTES + mainhub")
    p.add_argument("--dry-run", action="store_true", help="Print drafts only; no Telegram queue")
    p.add_argument("--force", action="store_true", help="Queue posts now (ignore weekday/hour)")
    p.add_argument("--since", default="7 days ago")
    p.add_argument("--top-k", type=int, default=8)
    args = p.parse_args()

    if args.dry_run:
        ctx = collect_weekly_build_log_context(since=args.since, max_commits=40)
        items = extract_build_log_items(ctx, top_k=args.top_k)
        week_key = _iso_week_key(datetime.now(timezone.utc))
        out = {
            "week": week_key,
            "commit_count": ctx.commit_count,
            "items": [{"label": i.label, "kind": i.kind, "source": i.source} for i in items],
            "patch_notes_html": draft_patch_notes_html(
                items,
                week_key=week_key,
                commit_count=ctx.commit_count,
                since_label=ctx.since_label,
            ),
            "mainhub_snippet_html": draft_mainhub_snippet_html(items, week_key=week_key),
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return

    db = SessionLocal()
    try:
        result = queue_weekly_build_log_posts(db, force=args.force)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if not result.get("ok"):
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
