#!/usr/bin/env python3
"""
Apply network-wide album_size=1 + Stars group-access checkout to all AOF schedulers/pools.

  cd tbcc/backend
  py -3.13 scripts/apply_network_album_checkout.py           # preview
  py -3.13 scripts/apply_network_album_checkout.py --execute
  py -3.13 scripts/apply_network_album_checkout.py --execute --sync-schedulers
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.services.aof_growth_hub import sync_network_album_and_checkout, sync_network_schedulers


def main() -> int:
    parser = argparse.ArgumentParser(description="AOF network album=1 + group-access checkout")
    parser.add_argument("--execute", action="store_true", help="Write changes (default: preview)")
    parser.add_argument(
        "--sync-schedulers",
        action="store_true",
        help="Also merge links-hub bulletin + channel promos before album/checkout pass",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report: dict = {}
        if args.sync_schedulers:
            report["schedulers"] = sync_network_schedulers(db, execute=args.execute)
        report["album_checkout"] = sync_network_album_and_checkout(db, execute=args.execute)
        if args.execute:
            db.commit()
        else:
            db.rollback()
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
