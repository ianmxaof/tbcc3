"""CLI: Storage Hub → R2 export ticks (run on island / local with Telethon).

  cd tbcc/backend
  py -3.13 scripts/export_storage_hub_to_r2.py --limit 5
  py -3.13 scripts/export_storage_hub_to_r2.py --drain --limit 20
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

for p in (ROOT.parent / ".env", ROOT / ".env"):
    if p.exists():
        load_dotenv(p, override=True)
        break


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Storage Hub media to R2")
    parser.add_argument("--since-id", type=int, default=0)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--drain", action="store_true", help="Loop until a batch exports nothing new")
    parser.add_argument("--include-existing", action="store_true", help="Do not skip rows that already have R2 keys")
    parser.add_argument("--media-id", type=int, default=0, help="Export a single media id")
    args = parser.parse_args()

    from app.database.session import SessionLocal
    from app.services.storage_hub_r2_export import export_one_media_to_r2, export_storage_hub_batch

    db = SessionLocal()
    try:
        if args.media_id:
            out = export_one_media_to_r2(db, args.media_id, force=args.include_existing)
            print(json.dumps(out, indent=2))
            return 0 if out.get("ok") else 1

        since = max(0, int(args.since_id))
        total_exported = 0
        total_failed = 0
        batches = 0
        while True:
            out = export_storage_hub_batch(
                db,
                since_id=since,
                limit=args.limit,
                only_missing_r2=not args.include_existing,
            )
            batches += 1
            total_exported += int(out.get("exported") or 0)
            total_failed += int(out.get("failed") or 0)
            since = int(out.get("next_since_id") or since)
            print(
                f"batch {batches}: count={out.get('count')} exported={out.get('exported')} "
                f"skipped={out.get('skipped')} failed={out.get('failed')} next_since={since}"
            )
            if not args.drain:
                break
            if int(out.get("exported") or 0) == 0 and int(out.get("count") or 0) == 0:
                break
            if int(out.get("exported") or 0) == 0 and int(out.get("failed") or 0) == 0:
                # Only skips — advance past this window by forcing since to next_since
                if int(out.get("count") or 0) == 0:
                    break
                # If we only skipped (already had R2), continue draining with raised since
                continue
        print(json.dumps({"exported": total_exported, "failed": total_failed, "batches": batches, "since": since}))
        return 1 if total_failed else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
