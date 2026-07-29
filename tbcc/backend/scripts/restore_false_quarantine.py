"""Restore loot media rejected by the infra-blind delivery quarantine (delivery_load_failed).

Those rows were marked stale because a Telethon batch timed out, not because Telegram confirmed
the Saved Message was gone. Only `delivery_load_failed` is restored; audit-confirmed
`saved_message_missing` / `delivery_saved_message_gone` rows stay quarantined.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.database.session import SessionLocal
from app.models.media import Media

RESTORE_REASONS = {"delivery_load_failed"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = parser.parse_args()

    restored = 0
    scanned = 0
    with SessionLocal() as db:
        rows = db.query(Media).filter(Media.status == "rejected", Media.tags.contains("stale_saved_msg")).all()
        for row in rows:
            scanned += 1
            try:
                payload = json.loads(row.classification_json or "{}")
            except json.JSONDecodeError:
                continue
            audit = payload.get("loot_audit") if isinstance(payload, dict) else None
            if not isinstance(audit, dict):
                continue
            if str(audit.get("reason") or "") not in RESTORE_REASONS:
                continue
            restored += 1
            if not args.apply:
                continue
            row.status = "approved"
            row.tags = ",".join(t.strip() for t in (row.tags or "").split(",") if t.strip() and t.strip() != "stale_saved_msg")
            payload.pop("loot_audit", None)
            row.classification_json = json.dumps(payload, separators=(",", ":")) if payload else None
        if args.apply:
            db.commit()

    print(f"scanned={scanned} restored={restored} applied={args.apply}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
