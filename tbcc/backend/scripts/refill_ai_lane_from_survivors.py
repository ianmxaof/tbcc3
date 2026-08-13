"""Rebuild AOF AI POOL rotation from media that is still deliverable.

The AI lane ran dry because AOF AI STORAGE deposits failed for a week and the surviving
approved rows point at dead Saved Messages. Two recoverable sources remain:

1. Local-disk rows (`local:` file ids) — bytes are on the volume, always sendable.
2. Previously posted AI STORAGE rows whose Saved Message still resolves.

Both are recycled AI content, not new. This buys the lane runway; it does not replace
fresh deposits into the storage topic.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.database.session import SessionLocal
from app.models.media import Media
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.telegram_admin import run_telegram_album_composer_io

AI_POOL_ID = 2
AI_SCHEDULER_ID = 2
AI_TOPIC_SOURCE = "topic:5978"
RECYCLE_TAG = "ai_lane_recycled"


async def _live_message_ids(candidates: list[int]) -> set[int]:
    """Which Saved Message ids still resolve to media (existence probe, no downloads)."""
    live: set[int] = set()

    async def _fn(storage) -> None:
        for start in range(0, len(candidates), 50):
            chunk = candidates[start : start + 50]
            try:
                msgs = await asyncio.wait_for(storage.client.get_messages("me", ids=chunk), timeout=45)
            except Exception as e:
                print(f"  probe chunk failed ({start}): {e}")
                continue
            for msg in msgs or []:
                if msg is not None and getattr(msg, "media", None):
                    live.add(int(msg.id))

    await run_telegram_album_composer_io(_fn)
    return live


def _tag(row: Media) -> None:
    tags = [t.strip() for t in (row.tags or "").split(",") if t.strip()]
    if RECYCLE_TAG not in tags:
        tags.append(RECYCLE_TAG)
    row.tags = ",".join(tags)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=80, help="max rows to return to rotation")
    args = parser.parse_args()

    with SessionLocal() as db:
        local_rows = (
            db.query(Media)
            .filter(
                Media.pool_id == AI_POOL_ID,
                Media.status.in_(["posted", "rejected"]),
                Media.file_id.like("local:%"),
            )
            .all()
        )
        print(f"local-disk AI rows (always deliverable): {len(local_rows)}")

        saved_rows = (
            db.query(Media)
            .filter(
                Media.pool_id == AI_POOL_ID,
                Media.status == "posted",
                Media.source_channel.contains(AI_TOPIC_SOURCE),
            )
            .all()
        )
        candidates = [int(r.telegram_message_id) for r in saved_rows if int(r.telegram_message_id or 0) > 0]
        print(f"AI STORAGE posted rows to probe: {len(candidates)}")

        live = asyncio.run(_live_message_ids(candidates)) if candidates else set()
        alive_rows = [r for r in saved_rows if int(r.telegram_message_id or 0) in live]
        print(f"  still live on Saved Messages: {len(alive_rows)}")

        restore = (local_rows + alive_rows)[: max(1, args.limit)]
        print(f"\nwould return to rotation: {len(restore)} rows")
        if not args.apply:
            print("(dry run — pass --apply)")
            return 0

        for row in restore:
            row.status = "approved"
            _tag(row)
        db.commit()

        approved = (
            db.query(Media).filter(Media.pool_id == AI_POOL_ID, Media.status == "approved").count()
        )
        print(f"AI pool approved now: {approved}")

        sched = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == AI_SCHEDULER_ID).first()
        if sched and approved > 0:
            sched.posting_auto_paused_at = None
            if hasattr(sched, "posting_auto_pause_reason"):
                sched.posting_auto_pause_reason = None
            db.commit()
            print("AI scheduler unpaused")
    return 0


if __name__ == "__main__":
    sys.exit(main())
