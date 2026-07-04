"""Auto-queue pack-worthy master archive URLs into AOF packs pool on ingest."""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.models.capture_archive_entry import CaptureArchiveEntry
from app.services.archive_governance import ARCHIVE_STATUS_APPROVED, normalize_archive_status

logger = logging.getLogger(__name__)


def archive_auto_pack_queue_enabled() -> bool:
    """When true, approved archive URLs that look like packs are queued immediately."""
    return (os.getenv("TBCC_ARCHIVE_AUTO_PACK_QUEUE") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def try_auto_queue_archive_entry_to_pack_pool(
    db: Session,
    row: CaptureArchiveEntry | None,
    *,
    enabled: bool | None = None,
    wire_scheduler: bool | None = None,
) -> dict[str, Any] | None:
    """
    Resolve + gate-wrap pack candidates into loot_modifiers (source_note=master_archive).
    Skips non-URLs, non-approved rows, and hosts that are not pack candidates.
    """
    if row is None:
        return None
    if enabled is False:
        return None
    if enabled is None and not archive_auto_pack_queue_enabled():
        return None
    if row.kind != "url":
        return None
    if normalize_archive_status(getattr(row, "status", None)) != ARCHIVE_STATUS_APPROVED:
        return None

    from app.services.loot_pack_pool import (
        auto_wire_packs_enabled,
        queue_archive_entry_to_pack_pool,
        refresh_aof_packs_scheduler,
    )

    try:
        result = queue_archive_entry_to_pack_pool(
            db,
            value=row.value,
            label=None,
            tags=row.tags,
            description=getattr(row, "description", None),
            archive_entry_id=row.id,
        )
    except Exception:
        logger.exception("archive pack autopilot failed id=%s", row.id)
        return {"ok": False, "error": "queue_failed"}

    if not result.get("ok") and not result.get("duplicate"):
        return result

    should_wire = wire_scheduler
    if should_wire is None:
        should_wire = auto_wire_packs_enabled()
    if should_wire and result.get("created"):
        try:
            result["scheduler"] = refresh_aof_packs_scheduler(db)
        except Exception:
            logger.exception("archive pack autopilot scheduler wire failed id=%s", row.id)

    if result.get("skipped"):
        logger.debug(
            "archive pack autopilot skip id=%s reason=%s",
            row.id,
            result.get("reason"),
        )
    elif result.get("created"):
        mod = result.get("modifier") or {}
        logger.info(
            "archive pack autopilot queued id=%s mod=%s url=%s",
            row.id,
            mod.get("id"),
            (row.value or "")[:80],
        )
    return result


def bulk_auto_queue_archive_entries(
    db: Session,
    entry_ids: list[int],
    *,
    enabled: bool | None = None,
    wire_scheduler: bool | None = None,
) -> dict[str, Any]:
    """Queue many archive rows after bulk ingest (dedupes by entry id)."""
    from app.services.loot_pack_pool import auto_wire_packs_enabled, refresh_aof_packs_scheduler

    ids = [int(x) for x in entry_ids if int(x) > 0]
    if not ids:
        return {"ok": True, "queued": 0, "skipped": 0, "duplicate": 0, "fail": 0}

    rows = (
        db.query(CaptureArchiveEntry)
        .filter(CaptureArchiveEntry.id.in_(ids))
        .order_by(CaptureArchiveEntry.id.asc())
        .all()
    )
    queued = dup = skipped = fail = 0
    results: list[dict[str, Any]] = []
    for row in rows:
        r = try_auto_queue_archive_entry_to_pack_pool(
            db,
            row,
            enabled=enabled,
            wire_scheduler=False,
        )
        if r is None:
            continue
        if r.get("skipped"):
            skipped += 1
        elif r.get("duplicate"):
            dup += 1
        elif r.get("created"):
            queued += 1
            results.append({"archive_id": row.id, "modifier_id": (r.get("modifier") or {}).get("id")})
        elif not r.get("ok"):
            fail += 1

    sched = None
    if wire_scheduler or (wire_scheduler is None and auto_wire_packs_enabled() and queued > 0):
        try:
            sched = refresh_aof_packs_scheduler(db)
        except Exception:
            logger.exception("bulk archive pack autopilot scheduler wire failed")

    return {
        "ok": True,
        "queued": queued,
        "duplicate": dup,
        "skipped": skipped,
        "fail": fail,
        "results": results,
        "scheduler": sched,
    }
