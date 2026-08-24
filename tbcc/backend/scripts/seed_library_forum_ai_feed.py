#!/usr/bin/env python3
"""Idempotent AI-topic feed seed for the AOF Library twin ("Archive of Filth",
Phase 2 of loot-forum-twin-week1). Creates exactly one new scheduled_text_posts
row targeting the twin's AI subtopic (thread_id=57), reusing the existing
AOF AI POOL's approved media. Does NOT touch any of the 11 public lane rows
apply_lane_cadence.py manages, and does not alter the public AI scheduler.

Dry-run by default — prints what WOULD be created, writes nothing. --execute
creates the channel row (if missing) and the scheduler row with
interval_minutes=288, which means the next Celery beat cycle after --execute
starts posting real content into the twin. Treat --execute as a deliberate,
separate, human-triggered step, not something to run reflexively after a
clean dry-run.

  py -3.13 scripts/seed_library_forum_ai_feed.py            # dry-run
  py -3.13 scripts/seed_library_forum_ai_feed.py --execute  # writes; goes live at next beat cycle

Re-running after --execute is a no-op (idempotent) — matches existing rows by name.
See tbcc/docs/handoffs/2026-08-22_loot-forum-twin-week1_report.md (Phase 2).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.aof_library_forum import (
    aof_library_forum_display_name,
    aof_library_forum_ident,
    aof_library_forum_invite,
)
from app.data.aof_library_forum_topic_map import AOF_LIBRARY_FORUM_WEEK1_FEED_THREAD_ID
from app.database.session import SessionLocal
from app.models.channel import Channel
from app.models.scheduled_text_post import ScheduledTextPost

SCHED_NAME = "AOF LIBRARY — AI topic (twin)"
AI_POOL_ID = 2  # AOF AI POOL — same approved media source as the public AI lane scheduler
INTERVAL_MINUTES = 288  # matches network cadence standard (CADENCE track); independent row
FALLBACK_CAPTION = (
    "\U0001f5dd️ <b>Archive of Filth — AI</b>\n"
    "Library feed. If you can read this, pool media wasn't picked up — flag it."
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Write changes (default dry-run)")
    args = parser.parse_args()

    ident = aof_library_forum_ident()
    invite = aof_library_forum_invite()
    display_name = aof_library_forum_display_name()
    thread_id = AOF_LIBRARY_FORUM_WEEK1_FEED_THREAD_ID

    db = SessionLocal()
    try:
        channel = db.query(Channel).filter(Channel.identifier == ident).first()
        if channel is None:
            print(f"{'CREATE' if args.execute else 'WOULD-CREATE'} channel identifier={ident} name={display_name!r}")
            if args.execute:
                channel = Channel(identifier=ident, name=f"{display_name} (twin)", invite_link=invite)
                db.add(channel)
                db.flush()
        else:
            print(f"OK     channel id={channel.id} identifier={ident} name={channel.name!r} already exists")

        sched = db.query(ScheduledTextPost).filter(ScheduledTextPost.name == SCHED_NAME).first()
        if sched is None:
            target_channel_id = channel.id if channel is not None else None
            print(
                f"{'CREATE' if args.execute else 'WOULD-CREATE'} scheduler name={SCHED_NAME!r} "
                f"channel_id={target_channel_id} thread={thread_id} pool_id={AI_POOL_ID} "
                f"interval={INTERVAL_MINUTES}m pool_only_mode=True album_size=1"
            )
            if args.execute:
                if channel is None:
                    raise RuntimeError("channel row missing after create attempt — flush failed")
                sched = ScheduledTextPost(
                    name=SCHED_NAME,
                    scheduler_category="manual",
                    channel_id=channel.id,
                    message_thread_id=thread_id,
                    content=FALLBACK_CAPTION,
                    pool_id=AI_POOL_ID,
                    pool_only_mode=True,
                    album_size=1,
                    interval_minutes=INTERVAL_MINUTES,
                )
                db.add(sched)
        else:
            print(
                f"OK     scheduler id={sched.id} channel_id={sched.channel_id} "
                f"thread={sched.message_thread_id} pool_id={sched.pool_id} interval={sched.interval_minutes}m"
            )

        if args.execute:
            db.commit()
            print("\nCommitted.")
        else:
            db.rollback()
            print("\nDry-run only — nothing written. Re-run with --execute to create and go live.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
