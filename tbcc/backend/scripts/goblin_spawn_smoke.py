#!/usr/bin/env python3
"""Print recent goblin drops + relay settings (island smoke)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.models.goblin_drop import GoblinDrop
from app.models.listening_relay_settings import ListeningRelaySettings


def main() -> int:
    db = SessionLocal()
    try:
        since = datetime.now(timezone.utc) - timedelta(days=3)
        drops = (
            db.query(GoblinDrop)
            .filter(GoblinDrop.created_at >= since)
            .order_by(GoblinDrop.id.desc())
            .limit(5)
            .all()
        )
        row = db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == 1).first()
        print(
            json.dumps(
                {
                    "goblin_mode_enabled": bool(getattr(row, "goblin_mode_enabled", False)),
                    "spawn_chance": float(getattr(row, "goblin_spawn_chance", 0) or 0),
                    "spawns_today": int(getattr(row, "goblin_spawns_today", 0) or 0),
                    "recent_drops": [
                        {
                            "id": d.id,
                            "channel_id": d.channel_id,
                            "status": d.status,
                            "created_at": str(d.created_at),
                        }
                        for d in drops
                    ],
                },
                indent=2,
            )
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
