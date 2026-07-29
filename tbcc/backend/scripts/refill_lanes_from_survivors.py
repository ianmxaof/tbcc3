"""Top up thin lane pools from media that is still deliverable.

Generalizes refill_ai_lane_from_survivors across the whole AOF network. For each content
lane below the depth target, recover rotation stock from two sources that can actually be
sent today:

1. Local-disk rows (`local:` file ids) — bytes live on the volume, never go stale.
2. Previously posted rows whose Saved Message reference still resolves.

Everything recovered is recycled content. This restores cadence on starved lanes; it does
not replace fresh deposits into the Storage Hub topics.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy.orm import Session

from app.data.aof_network import AOF_NETWORK_CHANNELS
from app.database.session import SessionLocal
from app.models.content_pool import ContentPool
from app.models.media import Media
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.telegram_admin import run_telegram_album_composer_io

RECYCLE_TAG = "lane_recycled"
SKIP_KEYS = {"inbox", "packs", "main"}


def _pool_for(db: Session, pool_name: str) -> ContentPool | None:
    return db.query(ContentPool).filter(ContentPool.name == pool_name).first()


def _local_rows(db: Session, pool_id: int) -> list[Media]:
    return (
        db.query(Media)
        .filter(
            Media.pool_id == pool_id,
            Media.status.in_(["posted", "rejected"]),
            Media.file_id.like("local:%"),
        )
        .all()
    )


def _posted_saved_rows(db: Session, pool_id: int, cap: int) -> list[Media]:
    return (
        db.query(Media)
        .filter(
            Media.pool_id == pool_id,
            Media.status == "posted",
            Media.telegram_message_id > 0,
            ~Media.file_id.like("local:%"),
        )
        .order_by(Media.id.desc())
        .limit(cap)
        .all()
    )


async def _probe_live(message_ids: list[int]) -> set[int]:
    """One Telethon pass for every lane — existence only, no downloads."""
    live: set[int] = set()
    if not message_ids:
        return live

    async def _fn(storage) -> None:
        for start in range(0, len(message_ids), 50):
            chunk = message_ids[start : start + 50]
            try:
                msgs = await asyncio.wait_for(storage.client.get_messages("me", ids=chunk), timeout=60)
            except Exception as e:
                print(f"  probe chunk {start} failed: {e}")
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
    parser.add_argument("--target", type=int, default=60, help="desired approved depth per lane")
    parser.add_argument("--probe-cap", type=int, default=120, help="max posted rows probed per lane")
    parser.add_argument("--unpause", action="store_true", help="clear auto-pause on refilled lanes")
    args = parser.parse_args()

    with SessionLocal() as db:
        plan: dict[str, dict] = {}
        probe_ids: list[int] = []

        for ch in AOF_NETWORK_CHANNELS:
            if ch.key in SKIP_KEYS:
                continue
            pool = _pool_for(db, ch.pool_name)
            if not pool:
                continue
            approved = (
                db.query(Media).filter(Media.pool_id == pool.id, Media.status == "approved").count()
            )
            need = max(0, args.target - approved)
            entry = {
                "key": ch.key,
                "pool_id": int(pool.id),
                "pool_name": ch.pool_name,
                "approved": approved,
                "need": need,
                "local": [],
                "saved": [],
            }
            plan[ch.key] = entry
            if need <= 0:
                continue
            entry["local"] = _local_rows(db, int(pool.id))
            entry["saved"] = _posted_saved_rows(db, int(pool.id), args.probe_cap)
            probe_ids.extend(int(r.telegram_message_id) for r in entry["saved"])

        print(f"probing {len(probe_ids)} Saved Message refs across thin lanes...\n")
        live = asyncio.run(_probe_live(probe_ids))

        total_restored = 0
        print(f"{'lane':<12} {'approved':>8} {'need':>5} {'local':>6} {'alive':>6} {'restore':>8}")
        for key, e in plan.items():
            if e["need"] <= 0:
                print(f"{key:<12} {e['approved']:>8} {0:>5} {'-':>6} {'-':>6} {'ok':>8}")
                continue
            alive = [r for r in e["saved"] if int(r.telegram_message_id) in live]
            restore = (list(e["local"]) + alive)[: e["need"]]
            e["restore"] = restore
            total_restored += len(restore)
            print(
                f"{key:<12} {e['approved']:>8} {e['need']:>5} "
                f"{len(e['local']):>6} {len(alive):>6} {len(restore):>8}"
            )

        print(f"\ntotal rows that would return to rotation: {total_restored}")
        if not args.apply:
            print("(dry run — pass --apply)")
            return 0

        for key, e in plan.items():
            rows = e.get("restore") or []
            if not rows:
                continue
            for row in rows:
                row.status = "approved"
                _tag(row)
            db.commit()
            if args.unpause:
                sched = (
                    db.query(ScheduledTextPost)
                    .filter(ScheduledTextPost.pool_id == e["pool_id"])
                    .filter(ScheduledTextPost.posting_auto_paused_at.isnot(None))
                    .all()
                )
                for s in sched:
                    s.posting_auto_paused_at = None
                    if hasattr(s, "posting_auto_pause_reason"):
                        s.posting_auto_pause_reason = None
                    print(f"  unpaused scheduler {s.id} ({key})")
                if sched:
                    db.commit()
            print(f"  {key}: +{len(rows)} approved")

    return 0


if __name__ == "__main__":
    sys.exit(main())
