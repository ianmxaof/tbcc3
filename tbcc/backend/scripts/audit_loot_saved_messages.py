"""
Audit loot-eligible media Saved Messages refs; quarantine dead rows.

Loot delivery downloads album bytes via Telethon from Saved Messages. Rows whose
telegram_message_id no longer exists in Saved Messages are skipped on every roll.

  cd tbcc/backend
  py -3 scripts/audit_loot_saved_messages.py                    # dry-run, all loot pools
  py -3 scripts/audit_loot_saved_messages.py --apply            # reject dead rows
  py -3 scripts/audit_loot_saved_messages.py --pool "AOF BOP POOL" --limit 200
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.content_pool import ContentPool
from app.models.loot import LootPoolEligibility
from app.models.media import Media


def _loot_pool_ids(db: Session, pool_names: list[str] | None) -> list[int]:
    q = (
        db.query(LootPoolEligibility.content_pool_id)
        .filter(LootPoolEligibility.loot_enabled.is_(True))
    )
    rows = [int(r[0]) for r in q.all()]
    if not pool_names:
        return rows
    name_set = {n.strip() for n in pool_names if n.strip()}
    pools = db.query(ContentPool).filter(ContentPool.id.in_(rows)).all()
    return [int(p.id) for p in pools if (p.name or "").strip() in name_set]


def _candidate_rows(
    db: Session,
    pool_ids: list[int],
    *,
    limit: int,
    max_message_id: int | None,
) -> list[Media]:
    q = (
        db.query(Media)
        .filter(
            Media.pool_id.in_(pool_ids),
            Media.status == "approved",
            Media.telegram_message_id > 0,
        )
        .order_by(Media.telegram_message_id.asc())
    )
    if max_message_id is not None and max_message_id > 0:
        q = q.filter(Media.telegram_message_id <= int(max_message_id))
    if limit > 0:
        q = q.limit(limit)
    return q.all()


async def _probe_saved(storage, telegram_message_id: int) -> bool:
    raw = await storage.client.get_messages("me", ids=int(telegram_message_id))
    msg = raw[0] if isinstance(raw, list) else raw
    return bool(msg and getattr(msg, "media", None))


def _quarantine_row(db: Session, row: Media) -> None:
    row.status = "rejected"
    tags = (row.tags or "").strip()
    if "stale_saved_msg" not in tags.split(","):
        row.tags = f"{tags},stale_saved_msg".strip(",") if tags else "stale_saved_msg"
    note = {
        "loot_audit": {
            "reason": "saved_message_missing",
            "telegram_message_id": int(row.telegram_message_id or 0),
        }
    }
    try:
        prior = json.loads(row.classification_json or "{}")
        if not isinstance(prior, dict):
            prior = {}
    except json.JSONDecodeError:
        prior = {}
    prior.update(note)
    row.classification_json = json.dumps(prior, separators=(",", ":"))


async def _run(args: argparse.Namespace) -> int:
    from app.services.telegram_admin import run_telegram_album_composer_io

    db = SessionLocal()
    try:
        pool_ids = _loot_pool_ids(db, args.pool)
        if not pool_ids:
            print("No loot-enabled pools matched.")
            return 1
        pools = {
            int(p.id): (p.name or f"pool-{p.id}")
            for p in db.query(ContentPool).filter(ContentPool.id.in_(pool_ids)).all()
        }
        rows = _candidate_rows(
            db,
            pool_ids,
            limit=int(args.limit or 0),
            max_message_id=args.max_message_id,
        )
        print(f"pools={len(pool_ids)} candidates={len(rows)} apply={args.apply}")
        if not rows:
            print("Nothing to audit.")
            return 0

        dead: list[Media] = []
        live = 0
        quarantined = 0

        async def _audit(storage) -> None:
            nonlocal live, quarantined
            for i, row in enumerate(rows, 1):
                tg_id = int(row.telegram_message_id or 0)
                ok = await _probe_saved(storage, tg_id)
                if ok:
                    live += 1
                else:
                    dead.append(row)
                    if args.apply:
                        _quarantine_row(db, row)
                        if len(dead) % max(1, int(args.batch)) == 0:
                            db.commit()
                            quarantined = len(dead)
                            print(f"  committed {quarantined} quarantined so far")
                if i % 25 == 0 or i == len(rows):
                    print(f"  probed {i}/{len(rows)} live={live} dead={len(dead)}")
                if args.pause_ms > 0:
                    await asyncio.sleep(args.pause_ms / 1000.0)

        await run_telegram_album_composer_io(_audit)

        print(f"RESULT live={live} dead={len(dead)}")
        for row in dead[:20]:
            pname = pools.get(int(row.pool_id or 0), "?")
            print(f"  DEAD media_id={row.id} saved={row.telegram_message_id} pool={pname}")
        if len(dead) > 20:
            print(f"  ... and {len(dead) - 20} more")

        if args.apply and dead:
            db.commit()
            print(f"QUARANTINED {len(dead)} rows (status=rejected, tag=stale_saved_msg)")
        elif dead and not args.apply:
            print("Dry-run only — re-run with --apply to quarantine dead rows.")
        return 0
    finally:
        db.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Audit loot Saved Messages refs")
    p.add_argument("--apply", action="store_true", help="Reject dead rows (quarantine)")
    p.add_argument("--pool", action="append", help="Limit to pool name(s); repeatable")
    p.add_argument("--limit", type=int, default=0, help="Max rows to probe (0=all)")
    p.add_argument(
        "--max-message-id",
        type=int,
        default=0,
        help="Only probe rows with telegram_message_id <= N (0=no cap)",
    )
    p.add_argument("--batch", type=int, default=50, help="Commit every N quarantines when --apply")
    p.add_argument("--pause-ms", type=int, default=50, help="Pause between probes (reduce session lock)")
    args = p.parse_args()
    if args.max_message_id <= 0:
        args.max_message_id = None
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
