#!/usr/bin/env python3
"""Refresh stored public funnel copy from retired Main references to Loot Room.

  cd tbcc/backend
  python scripts/apply_aof_public_copy_cutover.py
  python scripts/apply_aof_public_copy_cutover.py --execute
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
from app.services.aof_public_copy_cutover import apply_public_copy_cutover


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="DB-only AOF public copy cutover. Dry-run by default; no Telegram or Buffer posts."
    )
    parser.add_argument("--execute", action="store_true", help="Commit DB updates instead of rolling back")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report = apply_public_copy_cutover(db, execute=args.execute)
    finally:
        db.close()
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
