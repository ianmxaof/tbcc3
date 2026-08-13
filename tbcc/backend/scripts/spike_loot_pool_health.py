"""Quick loot pool health snapshot."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from sqlalchemy import func

from app.database.session import SessionLocal
from app.models.media import Media

POOLS = [2, 4, 9, 23]


def main() -> int:
    db = SessionLocal()
    try:
        for pid in POOLS:
            rows = (
                db.query(Media.status, func.count())
                .filter(Media.pool_id == pid)
                .group_by(Media.status)
                .all()
            )
            print(f"pool={pid}", dict(rows))
            live = (
                db.query(func.count())
                .filter(
                    Media.pool_id == pid,
                    Media.status == "approved",
                    Media.telegram_message_id > 100_000,
                )
                .scalar()
            )
            local = (
                db.query(func.count())
                .filter(
                    Media.pool_id == pid,
                    Media.status == "approved",
                    Media.file_id.like("local:%"),
                )
                .scalar()
            )
            print(f"  approved_new_saved={live} approved_local={local}")
            pending = (
                db.query(Media.id, Media.file_id, Media.telegram_message_id, Media.source_channel)
                .filter(Media.pool_id == pid, Media.status == "pending")
                .limit(3)
                .all()
            )
            if pending:
                print(f"  pending_sample={pending}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
