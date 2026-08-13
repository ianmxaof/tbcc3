#!/usr/bin/env python3
"""
Report duplicate pool rows that cause identical Telegram album tiles.

  cd tbcc/backend
  py -3.13 scripts/audit_pool_album_duplicates.py
  py -3.13 scripts/audit_pool_album_duplicates.py --pool "AOF ASS POOL"
  py -3.13 scripts/audit_pool_album_duplicates.py --execute-mark-posted  # demote dupes (careful)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from sqlalchemy import func

from app.database.session import SessionLocal
from app.models.content_pool import ContentPool
from app.models.media import Media


def _dup_groups(db, pool_id: int, *, status: str = "approved") -> dict:
    base = db.query(Media).filter(Media.pool_id == pool_id, Media.status == status)
    by_msg = (
        db.query(Media.telegram_message_id, func.count(Media.id))
        .filter(Media.pool_id == pool_id, Media.status == status, Media.telegram_message_id > 0)
        .group_by(Media.telegram_message_id)
        .having(func.count(Media.id) > 1)
        .all()
    )
    by_fu = (
        db.query(Media.file_unique_id, func.count(Media.id))
        .filter(Media.pool_id == pool_id, Media.status == status)
        .group_by(Media.file_unique_id)
        .having(func.count(Media.id) > 1)
        .all()
    )
    approved = base.count()
    distinct_msg = (
        db.query(func.count(func.distinct(Media.telegram_message_id)))
        .filter(Media.pool_id == pool_id, Media.status == status, Media.telegram_message_id > 0)
        .scalar()
        or 0
    )
    distinct_fu = (
        db.query(func.count(func.distinct(Media.file_unique_id)))
        .filter(Media.pool_id == pool_id, Media.status == status)
        .scalar()
        or 0
    )
    return {
        "approved_rows": int(approved),
        "distinct_telegram_message_id": int(distinct_msg),
        "distinct_file_unique_id": int(distinct_fu),
        "duplicate_message_groups": [
            {"telegram_message_id": int(tid), "count": int(cnt)} for tid, cnt in by_msg
        ],
        "duplicate_file_unique_groups": [
            {"file_unique_id": str(fu), "count": int(cnt)} for fu, cnt in by_fu
        ],
    }


def _demote_duplicates(db, pool_id: int) -> int:
    """Keep lowest id per telegram_message_id; mark extras posted so they stop surfacing."""
    rows = (
        db.query(Media)
        .filter(Media.pool_id == pool_id, Media.status == "approved", Media.telegram_message_id > 0)
        .order_by(Media.telegram_message_id.asc(), Media.id.asc())
        .all()
    )
    seen: dict[int, int] = {}
    demoted = 0
    for m in rows:
        tid = int(m.telegram_message_id)
        if tid in seen:
            m.status = "posted"
            demoted += 1
        else:
            seen[tid] = int(m.id)
    return demoted


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit pool rows that duplicate album tiles")
    parser.add_argument("--pool", action="append", dest="pools", help="Pool name (repeatable)")
    parser.add_argument(
        "--execute-mark-posted",
        action="store_true",
        help="Mark duplicate approved rows as posted (keeps lowest id per message)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        q = db.query(ContentPool).order_by(ContentPool.name.asc())
        if args.pools:
            q = q.filter(ContentPool.name.in_(args.pools))
        pools = q.all()
        report: list[dict] = []
        total_demoted = 0
        for pool in pools:
            entry = {
                "pool_id": pool.id,
                "pool_name": pool.name,
                "album_size": pool.album_size,
                "randomize_queue": bool(pool.randomize_queue),
                "auto_post_enabled": bool(pool.auto_post_enabled),
                **_dup_groups(db, int(pool.id)),
            }
            dup_msg = entry["duplicate_message_groups"]
            dup_fu = entry["duplicate_file_unique_groups"]
            entry["at_risk"] = bool(dup_msg or dup_fu)
            if args.execute_mark_posted and dup_msg:
                entry["demoted"] = _demote_duplicates(db, int(pool.id))
                total_demoted += int(entry["demoted"])
            report.append(entry)
        if args.execute_mark_posted:
            db.commit()
        else:
            db.rollback()
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(
            json.dumps(
                {
                    "pools": len(report),
                    "at_risk": sum(1 for r in report if r.get("at_risk")),
                    "demoted": total_demoted if args.execute_mark_posted else 0,
                    "rows": report,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
