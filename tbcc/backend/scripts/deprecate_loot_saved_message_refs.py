"""
Remove legacy Saved Messages refs from loot roll pools (local disk is canonical).

Fast SQL path — no Telethon. Use after TBCC_LOOT_LOCAL_BYTES_ONLY=1 is deployed.

  py -3 scripts/deprecate_loot_saved_message_refs.py              # dry-run
  py -3 scripts/deprecate_loot_saved_message_refs.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from sqlalchemy import and_, or_

from app.database.session import SessionLocal
from app.models.content_pool import ContentPool
from app.models.loot import LootPoolEligibility
from app.models.media import Media


def _loot_pool_ids(db) -> list[int]:
    rows = (
        db.query(LootPoolEligibility.content_pool_id)
        .filter(LootPoolEligibility.loot_enabled.is_(True))
        .all()
    )
    return [int(r[0]) for r in rows]


def main() -> int:
    p = argparse.ArgumentParser(description="Quarantine non-local loot pool media (Saved Messages refs)")
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    with SessionLocal() as db:
        pool_ids = _loot_pool_ids(db)
        if not pool_ids:
            print("No loot-enabled pools.")
            return 1
        pools = {
            int(p.id): (p.name or f"pool-{p.id}")
            for p in db.query(ContentPool).filter(ContentPool.id.in_(pool_ids)).all()
        }
        rows = (
            db.query(Media)
            .filter(
                Media.pool_id.in_(pool_ids),
                Media.status == "approved",
                or_(
                    Media.telegram_message_id > 0,
                    and_(Media.telegram_message_id == 0, ~Media.file_id.like("local:%")),
                ),
            )
            .all()
        )
        local_kept = (
            db.query(Media)
            .filter(
                Media.pool_id.in_(pool_ids),
                Media.status == "approved",
                Media.telegram_message_id == 0,
                Media.file_id.like("local:%"),
            )
            .count()
        )
        print(f"loot_pools={len(pool_ids)} deprecate_rows={len(rows)} local_approved_kept={local_kept} apply={args.apply}")
        by_pool: dict[str, int] = {}
        for row in rows:
            name = pools.get(int(row.pool_id or 0), "?")
            by_pool[name] = by_pool.get(name, 0) + 1
        for name, n in sorted(by_pool.items(), key=lambda x: -x[1])[:12]:
            print(f"  {name}: {n}")
        if not args.apply:
            return 0
        for row in rows:
            row.status = "rejected"
            tags = (row.tags or "").strip()
            if "deprecated_saved_msg" not in [t.strip() for t in tags.split(",") if t.strip()]:
                row.tags = f"{tags},deprecated_saved_msg".strip(",") if tags else "deprecated_saved_msg"
            note = {"loot_audit": {"reason": "deprecated_saved_msg_policy", "telegram_message_id": int(row.telegram_message_id or 0)}}
            try:
                prior = json.loads(row.classification_json or "{}")
                if not isinstance(prior, dict):
                    prior = {}
            except json.JSONDecodeError:
                prior = {}
            prior.update(note)
            row.classification_json = json.dumps(prior, separators=(",", ":"))
        db.commit()
        print(f"QUARANTINED {len(rows)} non-local loot rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
