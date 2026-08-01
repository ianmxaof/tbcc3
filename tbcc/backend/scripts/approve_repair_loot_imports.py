"""Approve pending repair imports in loot pools (emergency loot fix)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.models.media import Media

POOLS = [2, 4, 9, 23]


def main() -> int:
    db = SessionLocal()
    try:
        rows = (
            db.query(Media)
            .filter(
                Media.pool_id.in_(POOLS),
                Media.status == "pending",
            )
            .all()
        )
        approved = 0
        for row in rows:
            src = (row.source_channel or "").strip()
            if not src.startswith("repair:") and not str(row.file_id or "").startswith("local:"):
                continue
            row.status = "approved"
            approved += 1
        db.commit()
        print(f"approved_repair_pending={approved} scanned={len(rows)}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
