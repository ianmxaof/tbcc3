"""
Ensure LOOT ROOM content pools exist and stock them from matching AOF lane pools.

Clones approved Media rows (same Telegram Saved Message / file ids) into LOOT ROOM*
pools so loot rolls can use dedicated eligibility without emptying the public AOF pools.

  cd tbcc/backend
  py -3.13 scripts/stock_loot_room_pools.py              # dry-run
  py -3.13 scripts/stock_loot_room_pools.py --execute    # write
  py -3.13 scripts/stock_loot_room_pools.py --execute --per-pool 40
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.content_pool import ContentPool
from app.models.media import Media
from app.services.loot_pool_eligibility_seed import (
    seed_content_pool_loot_eligibility,
    seed_loot_room_pool_eligibility,
    tier_coverage_report,
)

# Source lane pool → dedicated loot floor pool
LANE_MAP: list[tuple[str, str]] = [
    ("AOF AI POOL", "LOOT ROOM FLOOR — AOF AI"),
    ("AOF ASS POOL", "LOOT ROOM FLOOR — AOF ASS"),
    ("AOF BIG TITS POOL", "LOOT ROOM FLOOR — AOF BIG TITS"),
    ("AOF BLOWJOB POOL", "LOOT ROOM FLOOR — AOF BLOWJOB"),
    ("AOF MILF POOL", "LOOT ROOM FLOOR — AOF MILF"),
    ("AOF TABOO POOL", "LOOT ROOM FLOOR — AOF TABOO"),
    ("AOF PUBLIC / VOYEUR POOL", "LOOT ROOM SPOTLIGHT — VOYEUR"),
    ("ABG / LBFM POOL", "LOOT ROOM SPOTLIGHT — ABG"),
    ("AOF MAIN GROUP POOL", "LOOT ROOM VAULT — MAIN"),
    # Packs promo is mostly local: R2 (no Saved Messages id on island) — use Main.
    ("AOF MAIN GROUP POOL", "LOOT ROOM VAULT — LOOT CHANNEL"),
]

LOOT_GROUP_CHANNEL_ID = 8


def _get_or_create_pool(db: Session, name: str) -> ContentPool:
    row = db.query(ContentPool).filter(ContentPool.name == name).first()
    if row:
        return row
    row = ContentPool(
        name=name,
        channel_id=LOOT_GROUP_CHANNEL_ID,
        album_size=5,
        interval_minutes=0,
        auto_post_enabled=False,
        randomize_queue=True,
    )
    db.add(row)
    db.flush()
    return row


def _clone_media(src: Media, dest_pool_id: int) -> Media:
    return Media(
        telegram_message_id=int(src.telegram_message_id),
        file_id=src.file_id,
        file_unique_id=src.file_unique_id,
        media_type=src.media_type,
        source_channel=src.source_channel,
        pool_id=int(dest_pool_id),
        tags=src.tags,
        nsfw_tier=src.nsfw_tier,
        classification_json=src.classification_json,
        status="approved",
    )


def stock(*, execute: bool, per_pool: int) -> dict:
    db = SessionLocal()
    report: dict = {"lanes": [], "eligibility": None, "tier_coverage": None}
    try:
        for src_name, dest_name in LANE_MAP:
            src = db.query(ContentPool).filter(ContentPool.name == src_name).first()
            if not src:
                # Fuzzy: name contains lane keyword
                key = src_name.replace(" POOL", "").replace("AOF ", "")
                src = (
                    db.query(ContentPool)
                    .filter(ContentPool.name.ilike(f"%{key}%"))
                    .filter(~ContentPool.name.ilike("LOOT ROOM%"))
                    .order_by(ContentPool.id.asc())
                    .first()
                )
            dest = _get_or_create_pool(db, dest_name) if execute else (
                db.query(ContentPool).filter(ContentPool.name == dest_name).first()
            )
            src_count = 0
            already = 0
            to_clone: list[Media] = []
            if src:
                src_count = (
                    db.query(func.count(Media.id))
                    .filter(Media.pool_id == int(src.id), Media.status == "approved")
                    .scalar()
                    or 0
                )
                if dest:
                    existing_uids = {
                        r[0]
                        for r in db.query(Media.file_unique_id)
                        .filter(Media.pool_id == int(dest.id))
                        .all()
                        if r[0]
                    }
                    already = len(existing_uids)
                    need = max(0, int(per_pool) - already)
                    if need > 0:
                        # Only clone rows the island can actually deliver (Saved Messages id).
                        q = (
                            db.query(Media)
                            .filter(
                                Media.pool_id == int(src.id),
                                Media.status == "approved",
                                Media.telegram_message_id.isnot(None),
                                Media.telegram_message_id > 0,
                            )
                            .order_by(Media.id.asc())
                        )
                        if existing_uids:
                            q = q.filter(~Media.file_unique_id.in_(list(existing_uids)))
                        to_clone = list(q.limit(need).all())
            lane = {
                "source": src.name if src else src_name,
                "source_id": int(src.id) if src else None,
                "source_approved": int(src_count),
                "dest": dest_name,
                "dest_id": int(dest.id) if dest else None,
                "dest_already": int(already),
                "would_clone": len(to_clone),
                "cloned": 0,
            }
            if execute and dest and to_clone:
                for m in to_clone:
                    db.add(_clone_media(m, int(dest.id)))
                lane["cloned"] = len(to_clone)
            report["lanes"].append(lane)

        if execute:
            db.commit()
            seed_loot_room_pool_eligibility(db)
            report["eligibility"] = seed_content_pool_loot_eligibility(db)
        report["tier_coverage"] = tier_coverage_report(db)
    finally:
        db.close()
    return report


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("--execute", action="store_true")
    p.add_argument("--per-pool", type=int, default=40, help="Target approved clones per LOOT ROOM pool")
    args = p.parse_args()
    print(json.dumps(stock(execute=args.execute, per_pool=args.per_pool), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
