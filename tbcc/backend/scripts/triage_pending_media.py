"""
Audit and triage pending media backlog.

  cd tbcc/backend
  py -3.13 scripts/triage_pending_media.py                    # report
  py -3.13 scripts/triage_pending_media.py --approve-non-packs
  py -3.13 scripts/triage_pending_media.py --rehome-packs-pending
  py -3.13 scripts/triage_pending_media.py --queue-goon-bop-imports --execute
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from sqlalchemy import func, update

from app.data.aof_network import AOF_NETWORK_CHANNELS, network_channel_by_key
from app.data.aof_storage_hub_map import AOF_STORAGE_TOPIC_MAP, network_key_for_storage_topic
from app.database.session import SessionLocal
from app.models.content_pool import ContentPool
from app.models.import_job import ImportJob
from app.models.media import Media

PACKS_POOL_NAME = "AOF PACKS — Promo"
PACKS_STORAGE_TOPIC_ID = 5980
_TOPIC_RE = re.compile(r"#topic:(\d+)")


def _pool_by_name(db, name: str) -> ContentPool | None:
    return db.query(ContentPool).filter(ContentPool.name == name).first()


def _network_pool_map(db) -> dict[str, ContentPool]:
    out: dict[str, ContentPool] = {}
    for ch in AOF_NETWORK_CHANNELS:
        row = db.query(ContentPool).filter(ContentPool.name == ch.pool_name).first()
        if row:
            out[ch.key] = row
    return out


def _topic_from_source(source: str | None) -> int | None:
    if not source:
        return None
    m = _TOPIC_RE.search(source)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def report(db) -> dict:
    total_pending = db.query(func.count(Media.id)).filter(Media.status == "pending").scalar() or 0
    by_pool = (
        db.query(ContentPool.name, func.count(Media.id))
        .join(Media, Media.pool_id == ContentPool.id)
        .filter(Media.status == "pending")
        .group_by(ContentPool.name)
        .order_by(func.count(Media.id).desc())
        .all()
    )
    goon = _pool_by_name(db, "AOF GOON POOL")
    bop = _pool_by_name(db, "AOF BOP POOL")
    packs = _pool_by_name(db, PACKS_POOL_NAME)

    def _counts(pool: ContentPool | None) -> dict:
        if not pool:
            return {}
        out = {}
        for st in ("pending", "approved", "rejected", "posted"):
            out[st] = (
                db.query(func.count(Media.id))
                .filter(Media.pool_id == pool.id, Media.status == st)
                .scalar()
                or 0
            )
        return out

    jobs = (
        db.query(ImportJob)
        .filter(ImportJob.job_kind == "channel")
        .order_by(ImportJob.created_at.desc())
        .limit(20)
        .all()
    )
    job_rows = []
    for j in jobs:
        params = {}
        if j.result_json:
            try:
                parsed = json.loads(j.result_json)
                if isinstance(parsed, dict):
                    params = parsed.get("params") if isinstance(parsed.get("params"), dict) else parsed
            except Exception:
                pass
        job_rows.append(
            {
                "id": j.id,
                "status": j.status,
                "stage": j.stage,
                "pool_id": j.pool_id,
                "topic": params.get("topic_title"),
                "error": (j.error_message or "")[:200] or None,
            }
        )

    return {
        "total_pending": int(total_pending),
        "by_pool": [{"pool": n, "pending": int(c)} for n, c in by_pool],
        "goon_pool": _counts(goon),
        "bop_pool": _counts(bop),
        "packs_pool": _counts(packs),
        "recent_channel_import_jobs": job_rows,
    }


def approve_non_packs(db, *, execute: bool) -> dict:
    packs = _pool_by_name(db, PACKS_POOL_NAME)
    exclude_id = int(packs.id) if packs else -1
    q = db.query(Media.id).filter(Media.status == "pending")
    if exclude_id > 0:
        q = q.filter(Media.pool_id != exclude_id)
    ids = [int(r[0]) for r in q.all()]
    if not execute:
        return {"would_approve": len(ids), "excluded_pool": PACKS_POOL_NAME}
    if not ids:
        return {"approved": 0}
    db.execute(update(Media).where(Media.id.in_(ids)).values(status="approved"))
    db.commit()
    return {"approved": len(ids), "excluded_pool": PACKS_POOL_NAME}


def rehome_packs_pending(db, *, execute: bool) -> dict:
    """Move misfiled pending rows out of AOF PACKS — Promo into lane pools via #topic: in source."""
    packs = _pool_by_name(db, PACKS_POOL_NAME)
    if not packs:
        return {"error": "packs_pool_not_found"}
    pools = _network_pool_map(db)
    pending = (
        db.query(Media)
        .filter(Media.pool_id == packs.id, Media.status == "pending")
        .order_by(Media.id.asc())
        .all()
    )
    moved: list[dict] = []
    kept: list[int] = []
    skipped: list[dict] = []
    for m in pending:
        src = (m.source_channel or "").strip()
        topic_id = _topic_from_source(src)
        if topic_id is None:
            # Promo uploads / local imports — keep in PACKS pool
            if src.startswith("import:") or "promo" in src.lower() or m.telegram_message_id == -1:
                kept.append(int(m.id))
            else:
                skipped.append({"id": m.id, "reason": "no_topic", "source": src[:120]})
            continue
        if topic_id == PACKS_STORAGE_TOPIC_ID:
            kept.append(int(m.id))
            continue
        net_key = network_key_for_storage_topic(topic_id)
        if not net_key or net_key == "packs":
            kept.append(int(m.id))
            continue
        target = pools.get(net_key)
        if not target:
            skipped.append({"id": m.id, "reason": f"no_pool_for_{net_key}", "topic_id": topic_id})
            continue
        dup = (
            db.query(Media.id)
            .filter(Media.pool_id == target.id, Media.file_unique_id == m.file_unique_id)
            .first()
        )
        if dup:
            skipped.append({"id": m.id, "reason": "duplicate_in_target", "target_pool": target.name})
            if execute:
                m.status = "rejected"
            continue
        entry = {
            "id": int(m.id),
            "from": PACKS_POOL_NAME,
            "to": target.name,
            "topic_id": topic_id,
        }
        if execute:
            m.pool_id = target.id
        moved.append(entry)

    if execute:
        db.commit()
    return {
        "execute": execute,
        "scanned": len(pending),
        "moved": moved,
        "kept_in_packs": len(kept),
        "skipped": skipped[:40],
        "skipped_total": len(skipped),
    }


def queue_goon_bop_imports(db, *, execute: bool, limit: int) -> dict:
    from app.services.aof_growth_hub import queue_storage_hub_deposits

    if not execute:
        return {"would_queue": ["goon", "bop"], "limit": limit}
    return queue_storage_hub_deposits(db, limit=limit, topic_keys=["goon", "bop"])


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Pending media triage")
    p.add_argument("--approve-non-packs", action="store_true", help="Approve all pending except AOF PACKS — Promo")
    p.add_argument("--rehome-packs-pending", action="store_true", help="Move misfiled PACKS pending → lane pools")
    p.add_argument("--queue-goon-bop-imports", action="store_true", help="Re-queue storage hub imports for GOON/BOP")
    p.add_argument("--execute", action="store_true", help="Apply changes (default: preview)")
    p.add_argument("--limit", type=int, default=50, help="Per-topic import limit for --queue-goon-bop-imports")
    args = p.parse_args()

    db = SessionLocal()
    try:
        out: dict = {"report": report(db)}
        if args.approve_non_packs:
            out["approve_non_packs"] = approve_non_packs(db, execute=args.execute)
        if args.rehome_packs_pending:
            out["rehome_packs"] = rehome_packs_pending(db, execute=args.execute)
        if args.queue_goon_bop_imports:
            out["goon_bop_imports"] = queue_goon_bop_imports(db, execute=args.execute, limit=args.limit)
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    finally:
        db.close()


if __name__ == "__main__":
    main()
