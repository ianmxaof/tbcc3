"""
One-time catch-up: enqueue tag-only backfill for existing approved media with
thin/empty tags, so more of the archive is reachable from keyword search.

Producer-only — enqueues Celery tasks over Redis, does not touch Telethon
directly. Safe to run from any host; the actual classify/download work runs
wherever the `telegram` queue worker lives (the island, per cloud-only policy).

  cd tbcc/backend
  py -3.13 scripts/backfill_media_tags.py --dry-run
  py -3.13 scripts/backfill_media_tags.py --apply --limit 500
  py -3.13 scripts/backfill_media_tags.py --apply --limit 5000 --pool-id 8 --stagger-s 5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=500, help="Max media rows to enqueue this run")
    ap.add_argument("--pool-id", type=int, default=None, help="Restrict to one content pool")
    ap.add_argument(
        "--thin-chars",
        type=int,
        default=None,
        help="media.tags shorter than this counts as needing backfill (default env / 24)",
    )
    ap.add_argument("--stagger-s", type=float, default=20.0, help="Seconds between enqueued items")
    ap.add_argument("--apply", action="store_true", help="Actually enqueue (default is a dry-run count)")
    ap.add_argument("--dry-run", action="store_true", help="Explicit no-op — same as omitting --apply")
    args = ap.parse_args()

    from app.database.session import SessionLocal
    from app.services.tag_backfill import find_thin_tag_media

    db = SessionLocal()
    try:
        media_ids = find_thin_tag_media(
            db, limit=args.limit, pool_id=args.pool_id, thin_chars=args.thin_chars
        )
    finally:
        db.close()

    print(f"Matched {len(media_ids)} media row(s) needing tag backfill (limit={args.limit}).")
    if not media_ids:
        return
    print(f"First few ids: {media_ids[:10]}")

    if not args.apply:
        print("\nDry-run only — pass --apply to enqueue. Nothing was queued.")
        return

    from app.workers.tag_backfill_worker import backfill_tag_media

    queued = 0
    for index, media_id in enumerate(media_ids):
        try:
            backfill_tag_media.apply_async(args=[media_id], countdown=index * args.stagger_s)
            queued += 1
        except Exception as exc:
            print(f"enqueue failed media_id={media_id}: {exc}")

    print(f"\nQueued {queued}/{len(media_ids)} — staggered {args.stagger_s}s apart.")
    print("Watch the telegram Celery queue depth; re-run with --pool-id to target a lane if it backs up.")


if __name__ == "__main__":
    main()
