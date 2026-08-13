#!/usr/bin/env python3
"""Queue Storage Hub deposits for thin content lanes + sync affiliate/schedulers."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from sqlalchemy import func

from app.data.aof_storage_hub_map import CONTENT_LANE_NETWORK_KEYS
from app.database.session import SessionLocal
from app.models.content_pool import ContentPool
from app.models.media import Media
from app.services.aof_growth_hub import (
    queue_storage_hub_deposits,
    sync_affiliate_network,
    sync_network_schedulers,
)
from app.services.export_flywheel_service import pool_id_for_network_key


def _approved_depth(db, pool_id: int | None) -> int:
    if not pool_id:
        return 0
    return int(
        db.query(func.count(Media.id))
        .filter(Media.pool_id == int(pool_id), Media.status == "approved")
        .scalar()
        or 0
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair thin AOF content lanes from Storage Hub")
    parser.add_argument("--execute", action="store_true", help="Queue imports (default dry-run)")
    parser.add_argument("--min-approved", type=int, default=12, help="Lanes below this get a deposit batch")
    parser.add_argument("--batch", type=int, default=12, help="Items per thin lane deposit")
    parser.add_argument("--lanes", type=str, default="", help="Comma-separated lane keys (default: all thin)")
    parser.add_argument("--sync-affiliates", dest="sync_affiliates", action="store_true", default=True)
    parser.add_argument("--no-sync-affiliates", dest="sync_affiliates", action="store_false")
    parser.add_argument("--sync-schedulers", dest="sync_schedulers", action="store_true", default=True)
    parser.add_argument("--no-sync-schedulers", dest="sync_schedulers", action="store_false")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        depths: dict[str, int] = {}
        for key in sorted(CONTENT_LANE_NETWORK_KEYS):
            pid = pool_id_for_network_key(db, key)
            depths[key] = _approved_depth(db, pid)

        allow = {k.strip().lower() for k in args.lanes.split(",") if k.strip()}
        thin = sorted(k for k, v in depths.items() if v < args.min_approved and (not allow or k in allow))
        report: dict = {
            "ok": True,
            "execute": args.execute,
            "min_approved": args.min_approved,
            "depths": depths,
            "thin_lanes": thin,
        }

        if args.execute and thin:
            report["deposits"] = queue_storage_hub_deposits(
                db,
                limit=args.batch,
                topic_keys=thin,
                media_types="both",
                content_lanes_only=False,
                include_topic_mirror=False,
            )
        if args.execute and args.sync_affiliates:
            report["affiliates"] = sync_affiliate_network(db, execute=True)
        if args.execute and args.sync_schedulers:
            report["schedulers"] = sync_network_schedulers(db, execute=True)
        if args.execute:
            db.commit()
        else:
            db.rollback()

        import json

        print(json.dumps(report, indent=2, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
