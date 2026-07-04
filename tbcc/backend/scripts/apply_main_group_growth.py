"""
Apply main-group growth: footer refresh, VIP Stars checkout on liveness, album checkout sync.

  cd tbcc/backend
  py -3.13 scripts/apply_main_group_growth.py --execute
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
from app.services.aof_network_liveness import apply_network_liveness, liveness_status


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("--execute", action="store_true")
    args = p.parse_args()

    db = SessionLocal()
    report: dict = {}
    try:
        report["liveness"] = apply_network_liveness(db, execute=args.execute)
        report["schedulers"] = sync_network_schedulers(db, execute=args.execute)
        report["checkout"] = sync_network_album_and_checkout(db, execute=args.execute)
        if args.execute:
            from app.services.aof_topic_mirror import queue_topic_mirror_all

            report["topic_mirror"] = queue_topic_mirror_all(db, limit_per_pair=8)
        if args.execute:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()

    db2 = SessionLocal()
    try:
        report["liveness_status"] = liveness_status(db2)
    finally:
        db2.close()
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
