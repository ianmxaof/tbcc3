"""
Seed AOF PACKS distribution channel + promo media pool (+ optional starter scheduler).

PACKS posts = promo image from pool + caption + inline buttons (LV mega link).
Mega inventory comes from loot_modifiers / link scrape — not the media pool.

  cd tbcc/backend && py -3.13 scripts/seed_aof_packs_channel.py
  py -3.13 scripts/seed_aof_packs_channel.py --execute
  py -3.13 scripts/seed_aof_packs_channel.py --execute --with-scheduler
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.mega_scrape_channel_sources import AOF_PACKS_CHANNEL_ID, AOF_PACKS_INVITE_URL
from app.database.session import SessionLocal
from app.models.channel import Channel
from app.models.content_pool import ContentPool
from app.models.scheduled_text_post import ScheduledTextPost

POOL_NAME = "AOF PACKS — Promo"
CHANNEL_NAME = "AOF PACKS"
PACKS_PLACEHOLDER_CAPTION = (
    "📦 **AOF PACK DROP**\n"
    "Curated mega — unlocked after one quick step.\n\n"
    "_More packs drop here daily. VIP skips the line: @aofsubscriptions_bot"
)


def seed(*, execute: bool, with_scheduler: bool) -> dict:
    ident = str(AOF_PACKS_CHANNEL_ID)
    report: dict = {"channel": None, "pool": None, "scheduler": None}

    db = SessionLocal()
    try:
        ch = db.query(Channel).filter(Channel.identifier == ident).first()
        if ch:
            report["channel"] = {"id": ch.id, "name": ch.name, "status": "exists"}
        else:
            report["channel"] = {
                "name": CHANNEL_NAME,
                "identifier": ident,
                "invite_link": AOF_PACKS_INVITE_URL,
                "status": "would_create",
            }
            if execute:
                ch = Channel(
                    name=CHANNEL_NAME,
                    identifier=ident,
                    invite_link=AOF_PACKS_INVITE_URL,
                )
                db.add(ch)
                db.flush()
                report["channel"] = {
                    "id": ch.id,
                    "name": ch.name,
                    "identifier": ident,
                    "status": "created",
                }

        if not ch:
            return report

        pool = db.query(ContentPool).filter(ContentPool.name == POOL_NAME).first()
        if pool:
            report["pool"] = {"id": pool.id, "name": pool.name, "status": "exists"}
        else:
            report["pool"] = {
                "name": POOL_NAME,
                "channel_id": ch.id,
                "album_size": 1,
                "status": "would_create",
            }
            if execute:
                pool = ContentPool(
                    name=POOL_NAME,
                    channel_id=ch.id,
                    album_size=1,
                    interval_minutes=0,
                    auto_post_enabled=False,
                    randomize_queue=True,
                )
                db.add(pool)
                db.flush()
                report["pool"] = {
                    "id": pool.id,
                    "name": pool.name,
                    "channel_id": ch.id,
                    "status": "created",
                }

        sched_name = "AOF PACKS — drop (manual)"
        existing_sched = (
            db.query(ScheduledTextPost)
            .filter(ScheduledTextPost.name == sched_name, ScheduledTextPost.channel_id == ch.id)
            .first()
        )
        if with_scheduler:
            buttons = json.dumps(
                [
                    {
                        "text": "⬇ Download Pack",
                        "url": "https://link-center.net/1367336/placeholder-replace-me",
                    },
                    {
                        "text": "⭐ VIP — skip ads",
                        "url": "https://t.me/aofsubscriptions_bot",
                    },
                ]
            )
            if existing_sched:
                report["scheduler"] = {"id": existing_sched.id, "status": "exists"}
            else:
                report["scheduler"] = {
                    "name": sched_name,
                    "channel_id": ch.id,
                    "pool_id": pool.id if pool else None,
                    "status": "would_create",
                    "note": "interval_minutes=NULL — trigger manually from dashboard until inventory flows",
                }
                if execute and pool:
                    db.add(
                        ScheduledTextPost(
                            name=sched_name,
                            channel_id=ch.id,
                            content=PACKS_PLACEHOLDER_CAPTION,
                            pool_id=pool.id,
                            album_size=1,
                            pool_only_mode=True,
                            pool_randomize=True,
                            buttons=buttons,
                            send_silent=False,
                            pin_after_send=False,
                            created_at=datetime.now(timezone.utc),
                        )
                    )
                    db.flush()
                    row = (
                        db.query(ScheduledTextPost)
                        .filter(ScheduledTextPost.name == sched_name, ScheduledTextPost.channel_id == ch.id)
                        .first()
                    )
                    if row:
                        report["scheduler"] = {
                            "id": row.id,
                            "name": sched_name,
                            "status": "created",
                            "note": "Replace placeholder LV URL in buttons before sending",
                        }

        if execute:
            db.commit()
    finally:
        db.close()
    return report


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("--execute", action="store_true")
    p.add_argument(
        "--with-scheduler",
        action="store_true",
        help="Create a manual (non-recurring) scheduled post bound to the promo pool",
    )
    args = p.parse_args()
    r = seed(execute=args.execute, with_scheduler=args.with_scheduler)
    print(json.dumps(r, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
