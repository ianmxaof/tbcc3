"""
Retire Buffer mirroring from the banned legacy main group; arm Loot Room hub scheduler.

  cd tbcc/backend
  py -3 scripts/retire_banned_main_buffer_mirror.py              # preview
  py -3 scripts/retire_banned_main_buffer_mirror.py --execute
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.aof_network import (
    BANNED_MAIN_GROUP_IDENT,
    MAIN_GROUP_IDENT,
    network_channel_by_key,
)
from app.database.session import SessionLocal
from app.models.channel import Channel
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.seed_aof_buffer_armory import LEGACY_MAIN_SCHEDULER_NAME


def apply(*, execute: bool) -> dict:
    loot_net = network_channel_by_key("main")
    db = SessionLocal()
    report: dict = {"execute": execute, "banned_channel": [], "loot_room": []}
    try:
        banned_ch = db.query(Channel).filter(Channel.identifier == BANNED_MAIN_GROUP_IDENT).first()
        if banned_ch:
            scheds = (
                db.query(ScheduledTextPost)
                .filter(ScheduledTextPost.channel_id == int(banned_ch.id))
                .all()
            )
            for sched in scheds:
                entry = {
                    "scheduler_id": sched.id,
                    "name": sched.name,
                    "buffer_before": bool(sched.buffer_mirror_enabled),
                }
                if execute:
                    sched.buffer_mirror_enabled = False
                    sched.buffer_publish_now = False
                entry["buffer_after"] = False
                report["banned_channel"].append(entry)

        loot_ch = db.query(Channel).filter(Channel.identifier == MAIN_GROUP_IDENT).first()
        if loot_ch and loot_net:
            sched = (
                db.query(ScheduledTextPost)
                .filter(
                    ScheduledTextPost.channel_id == int(loot_ch.id),
                    ScheduledTextPost.name.in_(
                        (loot_net.scheduler_name, LEGACY_MAIN_SCHEDULER_NAME)
                    ),
                )
                .order_by(ScheduledTextPost.id.asc())
                .first()
            )
            if sched:
                entry = {
                    "scheduler_id": sched.id,
                    "name_before": sched.name,
                    "buffer_before": bool(sched.buffer_mirror_enabled),
                }
                if execute:
                    sched.name = loot_net.scheduler_name
                    sched.buffer_mirror_enabled = True
                    sched.buffer_publish_now = False
                entry.update(
                    {
                        "name_after": loot_net.scheduler_name,
                        "buffer_after": True,
                        "buffer_publish_now": False,
                    }
                )
                report["loot_room"].append(entry)

        if execute:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()
    return report


def main() -> None:
    p = argparse.ArgumentParser(description="Retire banned-main Buffer; arm Loot Room hub")
    p.add_argument("--execute", action="store_true")
    args = p.parse_args()
    print(json.dumps(apply(execute=args.execute), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
