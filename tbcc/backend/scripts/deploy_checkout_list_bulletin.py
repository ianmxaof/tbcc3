#!/usr/bin/env python3
"""Sync + optionally post The Checkout List pinned deals board to Telegram.

  python scripts/deploy_checkout_list_bulletin.py --dry-run
  python scripts/deploy_checkout_list_bulletin.py --execute --post
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.services.checkout_list_hub import (
    build_checkout_list_bulletin,
    queue_checkout_list_bulletin_post,
    sync_checkout_list_hub,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy Checkout List SFW deals bulletin")
    parser.add_argument("--dry-run", action="store_true", help="Preview bulletin only")
    parser.add_argument("--execute", action="store_true", help="Upsert channel + scheduler rows")
    parser.add_argument("--post", action="store_true", help="Queue Telegram post (needs Celery post lane)")
    args = parser.parse_args()
    execute = args.execute or args.post
    if args.dry_run:
        execute = False

    db = SessionLocal()
    try:
        bulletin = build_checkout_list_bulletin(db)
        print("--- bulletin preview ---")
        print(bulletin)
        print("--- end preview ---")

        if args.dry_run:
            report = sync_checkout_list_hub(db, execute=False)
            print(json.dumps(report, indent=2))
            return 0

        if not execute:
            print("Pass --execute or --post to write DB rows.")
            return 0

        if args.post:
            report = queue_checkout_list_bulletin_post(db)
            db.commit()
        else:
            report = sync_checkout_list_hub(db, execute=True)
            db.commit()
        print(json.dumps(report, indent=2, default=str))
        return 0 if report.get("ok", True) else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
