#!/usr/bin/env python3
"""Ensure AOF FULL LENGTH channel, pool, and tag-driven scheduler exist in TBCC DB."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.services.aof_full_length_pool import (
    DISPLAY_NAME,
    POOL_NAME,
    SCHED_NAME,
    configure_full_length_pool,
    refresh_aof_full_length_scheduler,
)
from app.models.channel import Channel
from app.models.content_pool import ContentPool
from app.models.scheduled_text_post import ScheduledTextPost


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Register AOF FULL LENGTH channel + pool + scheduler")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--channel-ident", type=str, default="", help="Telegram channel id (-100…)")
    parser.add_argument("--invite", type=str, default="", help="t.me/+ invite link")
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=360,
        help="Scheduler cadence (default 360 = 6h between feature drops)",
    )
    args = parser.parse_args()

    ident = (args.channel_ident or "").strip()
    invite = (args.invite or "").strip()
    if args.execute and not ident:
        print(json.dumps({"error": "channel_ident_required_for_execute"}, indent=2))
        return 1

    db = SessionLocal()
    report: dict = {
        "pool_name": POOL_NAME,
        "scheduler_name": SCHED_NAME,
        "display_name": DISPLAY_NAME,
        "channel_ident": ident or None,
        "fifo_chronological": True,
        "send_time_tag_caption": True,
    }
    try:
        ch = None
        if ident:
            ch = db.query(Channel).filter(Channel.identifier == ident).first()
        if ch:
            report["channel"] = {"id": ch.id, "status": "exists"}
            if args.execute:
                ch.name = DISPLAY_NAME
                if invite:
                    ch.invite_link = invite
        elif ident:
            report["channel"] = {"status": "would_create" if not args.execute else "created"}
            if args.execute:
                ch = Channel(name=DISPLAY_NAME, identifier=ident, invite_link=invite or None)
                db.add(ch)
                db.flush()
                report["channel"]["id"] = ch.id

        pool = db.query(ContentPool).filter(ContentPool.name == POOL_NAME).first()
        if pool:
            report["pool"] = {"id": pool.id, "status": "exists"}
            if args.execute:
                configure_full_length_pool(pool)
                if ch:
                    pool.channel_id = ch.id
        else:
            report["pool"] = {"status": "would_create" if not args.execute else "created"}
            if args.execute and ch:
                pool = ContentPool(
                    name=POOL_NAME,
                    channel_id=ch.id,
                    album_size=1,
                    interval_minutes=0,
                    auto_post_enabled=True,
                    randomize_queue=False,
                )
                db.add(pool)
                db.flush()
                report["pool"]["id"] = pool.id

        sched = db.query(ScheduledTextPost).filter(ScheduledTextPost.name == SCHED_NAME).first()
        if sched:
            report["scheduler"] = {"id": sched.id, "status": "exists"}
            if args.execute and ch and pool:
                sched.channel_id = ch.id
                sched.pool_id = pool.id
                sched.interval_minutes = max(60, int(args.interval_minutes))
        else:
            report["scheduler"] = {"status": "would_create" if not args.execute else "created"}
            if args.execute and ch and pool:
                sched = ScheduledTextPost(
                    name=SCHED_NAME,
                    channel_id=ch.id,
                    content="🎬 <b>AOF FULL LENGTH</b>",
                    pool_id=pool.id,
                    album_size=1,
                    pool_only_mode=True,
                    pool_randomize=False,
                    interval_minutes=max(60, int(args.interval_minutes)),
                    created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
                db.add(sched)
                db.flush()
                report["scheduler"]["id"] = sched.id

        if args.execute:
            db.commit()
            wire = refresh_aof_full_length_scheduler(db)
            report["wire"] = wire
        else:
            db.rollback()
    finally:
        db.close()

    report["next_steps"] = [
        "Create Telegram channel (suggested: AOF FULL LENGTH with film emoji)",
        "Set AOF_FULL_LENGTH_IDENT + AOF_FULL_LENGTH_INVITE in app/data/aof_network.py (or re-run with --channel-ident)",
        "Add Storage Hub subtopic + row in app/data/aof_storage_hub_map.py",
        "Deposit: py -3.13 scripts/deposit_storage_hub_to_pools.py --execute --topics full_length",
        "Ensure TBCC_CLIP_CATEGORIZE_URL is up so imports auto-tag on pool deposit",
    ]
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
