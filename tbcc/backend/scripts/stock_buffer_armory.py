"""Arm TBCC buffer_x_queue with AOF X promo captions (relay + scheduler). Run from tbcc/backend."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.services.aof_social_links import (
    aof_gate_url,
    allmylinks_url,
    gravatar_profile_url,
)
from app.services.seed_aof_buffer_armory import (
    build_armory_queue_items,
    seed_relay_buffer_armory,
    seed_scheduled_buffer_armory,
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Stock TBCC Buffer X armory (trigger-synced queue)")
    p.add_argument("--preview", action="store_true", help="Print resolved captions only")
    p.add_argument("--relay", action="store_true", help="Arm listening relay buffer_x_queue")
    p.add_argument("--scheduled", action="store_true", help="Arm scheduled posts with buffer_mirror")
    p.add_argument("--post-id", type=int, default=None, help="Single scheduled post id")
    p.add_argument("--append", action="store_true", help="Append instead of replace")
    args = p.parse_args()

    print("links:", file=sys.stderr)
    print(f"  gate: {aof_gate_url()}", file=sys.stderr)
    print(f"  allmylinks: {allmylinks_url() or '(unset — using hub)'}", file=sys.stderr)
    print(f"  gravatar: {gravatar_profile_url() or '(unset)'}", file=sys.stderr)

    items = build_armory_queue_items()
    if args.preview or not (args.relay or args.scheduled):
        print(json.dumps(items, indent=2, ensure_ascii=False))
        print(f"\n{len(items)} armory items (consumed 1 per Telegram→Buffer trigger)", file=sys.stderr)
        if not args.relay and not args.scheduled:
            print("Use --relay and/or --scheduled to arm TBCC queues.", file=sys.stderr)
        return

    db = SessionLocal()
    try:
        if args.relay:
            n = seed_relay_buffer_armory(db, replace=not args.append)
            print(f"relay: armed {n} items", file=sys.stderr)
        if args.scheduled:
            n = seed_scheduled_buffer_armory(
                db,
                post_id=args.post_id,
                replace=not args.append,
            )
            print(f"scheduled: armed {n} post(s)", file=sys.stderr)
        if args.relay:
            from app.models.listening_relay_settings import ListeningRelaySettings

            row = db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == 1).first()
            remaining = len(row.get_buffer_x_queue()) if row else 0
            print(f"relay queue depth: {remaining}", file=sys.stderr)
    finally:
        db.close()


if __name__ == "__main__":
    main()
