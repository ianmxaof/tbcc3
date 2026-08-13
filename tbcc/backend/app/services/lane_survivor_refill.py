"""Recycle deliverable pool media back into approved rotation (lane survivor refill)."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.data.aof_network import AOF_NETWORK_CHANNELS
from app.models.content_pool import ContentPool
from app.models.media import Media
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.local_media_storage import local_media_path
from app.services.telegram_admin import run_telegram_album_composer_io

logger = logging.getLogger(__name__)

RECYCLE_TAG = "lane_recycled"
SKIP_KEYS = {"inbox", "packs", "main"}


@dataclass
class LaneRefillPlan:
    key: str
    pool_id: int
    pool_name: str
    approved: int
    need: int
    local: list[Media] = field(default_factory=list)
    saved: list[Media] = field(default_factory=list)
    restore: list[Media] = field(default_factory=list)


def lane_survivor_refill_enabled() -> bool:
    raw = (os.getenv("TBCC_LANE_SURVIVOR_REFILL_ENABLED") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _pool_for(db: Session, pool_name: str) -> ContentPool | None:
    return db.query(ContentPool).filter(ContentPool.name == pool_name).first()


def _local_rows(db: Session, pool_id: int) -> list[Media]:
    rows = (
        db.query(Media)
        .filter(
            Media.pool_id == pool_id,
            Media.status.in_(["posted", "rejected"]),
            Media.file_id.like("local:%"),
        )
        .all()
    )
    deliverable: list[Media] = []
    for row in rows:
        path = local_media_path(row.file_id)
        if path and os.path.isfile(path):
            deliverable.append(row)
    return deliverable


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
    live: set[int] = set()
    if not message_ids:
        return live

    async def _fn(storage) -> None:
        for start in range(0, len(message_ids), 50):
            chunk = message_ids[start : start + 50]
            try:
                msgs = await asyncio.wait_for(storage.client.get_messages("me", ids=chunk), timeout=60)
            except Exception as e:
                logger.warning("lane survivor probe chunk %s failed: %s", start, e)
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


def build_lane_survivor_refill_plan(
    db: Session,
    *,
    target: int = 60,
    probe_cap: int = 120,
) -> tuple[dict[str, LaneRefillPlan], list[int]]:
    plan: dict[str, LaneRefillPlan] = {}
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
        need = max(0, target - approved)
        entry = LaneRefillPlan(
            key=ch.key,
            pool_id=int(pool.id),
            pool_name=ch.pool_name,
            approved=approved,
            need=need,
        )
        plan[ch.key] = entry
        if need <= 0:
            continue
        entry.local = _local_rows(db, int(pool.id))
        entry.saved = _posted_saved_rows(db, int(pool.id), probe_cap)
        probe_ids.extend(int(r.telegram_message_id) for r in entry.saved)

    return plan, probe_ids


def apply_lane_survivor_refill_plan(
    db: Session,
    plan: dict[str, LaneRefillPlan],
    live: set[int],
    *,
    unpause: bool = False,
) -> dict[str, int]:
    restored_by_lane: dict[str, int] = {}
    for key, entry in plan.items():
        if entry.need <= 0:
            continue
        alive = [r for r in entry.saved if int(r.telegram_message_id) in live]
        restore = (list(entry.local) + alive)[: entry.need]
        entry.restore = restore
        if not restore:
            continue
        for row in restore:
            row.status = "approved"
            _tag(row)
        db.commit()
        restored_by_lane[key] = len(restore)
        if unpause:
            scheds = (
                db.query(ScheduledTextPost)
                .filter(ScheduledTextPost.pool_id == entry.pool_id)
                .filter(ScheduledTextPost.posting_auto_paused_at.isnot(None))
                .all()
            )
            for s in scheds:
                s.posting_auto_paused_at = None
                if hasattr(s, "posting_auto_pause_reason"):
                    s.posting_auto_pause_reason = None
            if scheds:
                db.commit()
    return restored_by_lane


def refill_lanes_from_survivors_sync(
    db: Session,
    *,
    target: int = 60,
    probe_cap: int = 120,
    execute: bool = False,
    unpause: bool = False,
) -> dict:
    plan, probe_ids = build_lane_survivor_refill_plan(db, target=target, probe_cap=probe_cap)
    live = asyncio.run(_probe_live(probe_ids)) if probe_ids else set()

    preview: dict[str, dict] = {}
    total = 0
    for key, entry in plan.items():
        if entry.need <= 0:
            preview[key] = {"approved": entry.approved, "need": 0, "restore": 0}
            continue
        alive = [r for r in entry.saved if int(r.telegram_message_id) in live]
        restore_n = len((list(entry.local) + alive)[: entry.need])
        total += restore_n
        preview[key] = {
            "approved": entry.approved,
            "need": entry.need,
            "local": len(entry.local),
            "alive": len(alive),
            "restore": restore_n,
        }

    report: dict = {
        "ok": True,
        "execute": execute,
        "target": target,
        "probed": len(probe_ids),
        "would_restore": total,
        "lanes": preview,
    }
    if not execute:
        return report

    restored = apply_lane_survivor_refill_plan(db, plan, live, unpause=unpause)
    report["restored"] = restored
    report["restored_total"] = sum(restored.values())
    return report
