"""
Re-import loot pools from AOF channels (local disk) + approve fresh rows.

Use after audit_loot_saved_messages.py quarantines stale Saved Messages refs.

  cd tbcc/backend
  py -3 scripts/repair_loot_pool_channels.py --dry-run
  py -3 scripts/repair_loot_pool_channels.py --limit 40
  py -3 scripts/repair_loot_pool_channels.py --audit-apply --limit 40
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.models.content_pool import ContentPool
from app.models.media import Media
from app.services.media_gatekeeper import gatekeeper_verdict_from_media

# Pools that failed in the 2026-07-24 key-roll incident.
REPAIR_TARGETS: list[tuple[str, str]] = [
    ("AOF BOP POOL", "-1003763051030"),
    ("AOF BIG TITS POOL", "-1003953321276"),
    ("ABG / LBFM POOL", "-1003984584735"),
    ("AOF AI POOL", "-1003997525573"),
]


def _resolve_pool(db, name: str) -> ContentPool | None:
    return db.query(ContentPool).filter(ContentPool.name == name).first()


def _approve_fresh_local(db, pool_id: int) -> int:
    rows = (
        db.query(Media)
        .filter(
            Media.pool_id == int(pool_id),
            Media.status == "pending",
            Media.file_id.like("local:%"),
        )
        .all()
    )
    approved = 0
    for row in rows:
        verdict = gatekeeper_verdict_from_media(row)
        if verdict in ("reject", "quarantine"):
            continue
        row.status = "approved"
        approved += 1
    if approved:
        db.commit()
    return approved


async def _import_pool(db, *, pool: ContentPool, channel: str, limit: int, dry_run: bool) -> dict:
    if dry_run:
        return {"pool": pool.name, "dry_run": True, "channel": channel, "limit": limit}

    from app.services.telegram_admin import run_telegram_import_io, run_telegram_io

    source = f"repair:{channel}"

    async def _fn(storage):
        return await storage.import_from_telegram_channel(
            channel,
            int(pool.id),
            source,
            db,
            limit=limit,
            media_types="both",
        )

    try:
        result = await run_telegram_import_io(_fn)
    except RuntimeError as e:
        if "import session is not logged in" not in str(e).lower():
            raise
        print(f"  import session unavailable, falling back to admin session: {e}")
        result = await run_telegram_io(_fn)
    approved = _approve_fresh_local(db, int(pool.id))
    return {**result, "pool": pool.name, "approved_pending": approved}


def _run_audit_apply(audit_limit: int) -> None:
    audit = Path(__file__).resolve().parent / "audit_loot_saved_messages.py"
    cmd = [
        sys.executable,
        str(audit),
        "--apply",
        "--max-message-id",
        "100000",
    ]
    if audit_limit > 0:
        cmd.extend(["--limit", str(audit_limit)])
    for pool_name, _channel in REPAIR_TARGETS:
        cmd.extend(["--pool", pool_name])
    print("AUDIT", " ".join(cmd))
    subprocess.run(cmd, check=True)


async def _run(args: argparse.Namespace) -> int:
    if args.audit_apply:
        _run_audit_apply(int(args.audit_limit or 0))

    db = SessionLocal()
    try:
        for pool_name, channel in REPAIR_TARGETS:
            pool = _resolve_pool(db, pool_name)
            if pool is None:
                print(f"SKIP missing pool: {pool_name}")
                continue
            print(f"IMPORT {pool_name} (id={pool.id}) channel={channel} limit={args.limit}")
            out = await _import_pool(
                db,
                pool=pool,
                channel=channel,
                limit=int(args.limit),
                dry_run=bool(args.dry_run),
            )
            print(f"  -> {out}")
        return 0
    finally:
        db.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Re-import loot pools from AOF channels")
    p.add_argument("--limit", type=int, default=40, help="New items per pool (deduped)")
    p.add_argument("--dry-run", action="store_true", help="Print plan only")
    p.add_argument(
        "--audit-apply",
        action="store_true",
        help="Quarantine stale saved-message rows in these pools first",
    )
    p.add_argument(
        "--audit-limit",
        type=int,
        default=0,
        help="Cap audit probe count when --audit-apply (0=all under max-id)",
    )
    args = p.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
