"""
Fast SQL quarantine for stale Saved Messages refs (no Telethon probe).

  py -3 scripts/quarantine_stale_loot_saved_sql.py --dry-run
  py -3 scripts/quarantine_stale_loot_saved_sql.py --apply --max-message-id 100000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from sqlalchemy import text

from app.database.session import SessionLocal
from app.models.content_pool import ContentPool

DEFAULT_POOLS = [
    "AOF BOP POOL",
    "AOF BIG TITS POOL",
    "ABG / LBFM POOL",
    "AOF AI POOL",
]


def main() -> int:
    p = argparse.ArgumentParser(description="SQL quarantine stale loot saved-message refs")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--max-message-id", type=int, default=100_000)
    p.add_argument("--pool", action="append")
    args = p.parse_args()

    names = args.pool or DEFAULT_POOLS
    db = SessionLocal()
    try:
        pools = db.query(ContentPool).filter(ContentPool.name.in_(names)).all()
        pool_ids = [int(p.id) for p in pools]
        if not pool_ids:
            print("No pools matched:", names)
            return 1

        count = db.execute(
            text(
                """
                SELECT COUNT(*) FROM media
                WHERE pool_id = ANY(:pool_ids)
                  AND status = 'approved'
                  AND telegram_message_id > 0
                  AND telegram_message_id <= :max_id
                """
            ),
            {"pool_ids": pool_ids, "max_id": int(args.max_message_id)},
        ).scalar()
        print(f"pools={[p.name for p in pools]} stale_approved={count} apply={args.apply}")
        if not args.apply or not count:
            return 0

        updated = db.execute(
            text(
                """
                UPDATE media
                SET status = 'rejected',
                    tags = CASE
                        WHEN tags IS NULL OR tags = '' THEN 'stale_saved_msg'
                        WHEN tags LIKE '%stale_saved_msg%' THEN tags
                        ELSE tags || ',stale_saved_msg'
                    END
                WHERE pool_id = ANY(:pool_ids)
                  AND status = 'approved'
                  AND telegram_message_id > 0
                  AND telegram_message_id <= :max_id
                """
            ),
            {"pool_ids": pool_ids, "max_id": int(args.max_message_id)},
        ).rowcount
        db.commit()
        print(f"QUARANTINED {updated}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
