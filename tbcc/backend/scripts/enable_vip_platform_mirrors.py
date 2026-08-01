"""
Enable Erome + Reddit mirrors on VIP and main schedulers (island).

  cd tbcc/backend
  py -3.13 scripts/enable_vip_platform_mirrors.py              # preview
  py -3.13 scripts/enable_vip_platform_mirrors.py --execute
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.aof_network import AOF_NETWORK_CHANNELS, MAIN_GROUP_IDENT, AOF_VIP_IDENT
from app.database.session import SessionLocal
from app.models.channel import Channel
from app.models.scheduled_text_post import ScheduledTextPost

TARGET_IDENTS = {AOF_VIP_IDENT, MAIN_GROUP_IDENT}
MIRROR_NAMES = (
    "AOF LOOT ROOM + X SCHEDULER",
    "AOF MAIN GROUP + X SCHEDULER",  # legacy name until retire script renames row
    "AOF VIP SCHEDULER",
)


def apply(*, execute: bool) -> dict:
    db = SessionLocal()
    updated: list[dict] = []
    try:
        for ident in TARGET_IDENTS:
            ch = db.query(Channel).filter(Channel.identifier == ident).first()
            if not ch:
                updated.append({"identifier": ident, "status": "channel_missing"})
                continue
            scheds = db.query(ScheduledTextPost).filter(ScheduledTextPost.channel_id == ch.id).all()
            for sched in scheds:
                if "MAINHUB" in (sched.name or "").upper():
                    continue
                entry = {
                    "scheduler_id": sched.id,
                    "name": sched.name,
                    "channel": ident,
                    "erome_before": bool(sched.erome_mirror_enabled),
                    "reddit_before": bool(sched.reddit_mirror_enabled),
                }
                if execute:
                    sched.erome_mirror_enabled = True
                    sched.reddit_mirror_enabled = True
                    sched.buffer_mirror_enabled = True
                entry["erome_after"] = True
                entry["reddit_after"] = True
                updated.append(entry)
        if execute:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()
    return {"execute": execute, "updated": updated, "note": "Reddit live requires TBCC_REDDIT_EXECUTE=1"}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--execute", action="store_true")
    args = p.parse_args()
    print(json.dumps(apply(execute=args.execute), indent=2))


if __name__ == "__main__":
    main()
