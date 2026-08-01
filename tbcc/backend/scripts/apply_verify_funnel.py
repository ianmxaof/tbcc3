"""
Deploy Collab.Land-style verify funnel — Loot Room pin + operator URLs.

  cd tbcc/backend
  py -3 scripts/apply_verify_funnel.py              # preview
  py -3 scripts/apply_verify_funnel.py --execute
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Apply verify funnel pin to Loot Room")
    p.add_argument("--execute", action="store_true")
    args = p.parse_args()

    from app.database.session import SessionLocal
    from app.data.aof_network import MAIN_GROUP_IDENT
    from app.models.channel import Channel
    from app.models.scheduled_text_post import ScheduledTextPost
    from app.services.verify_funnel import (
        VERIFY_FUNNEL_SCHED_NAME,
        build_loot_room_verify_pin_html,
        verify_deep_link,
        verify_funnel_enabled,
    )

    db = SessionLocal()
    try:
        ch = db.query(Channel).filter(Channel.identifier == MAIN_GROUP_IDENT).first()
        if not ch:
            raise SystemExit("Loot Room channel not found — sync aof_network first")

        content = build_loot_room_verify_pin_html()
        sched = (
            db.query(ScheduledTextPost)
            .filter(
                ScheduledTextPost.channel_id == ch.id,
                ScheduledTextPost.name == VERIFY_FUNNEL_SCHED_NAME,
            )
            .first()
        )
        report: dict = {
            "enabled": verify_funnel_enabled(),
            "channel": ch.name,
            "channel_id": ch.id,
            "vip_deep_link": verify_deep_link("vip"),
            "loot_deep_link": verify_deep_link("loot_room"),
            "chars": len(content),
        }
        if not sched:
            report["status"] = "would_create"
            if args.execute:
                sched = ScheduledTextPost(
                    name=VERIFY_FUNNEL_SCHED_NAME,
                    channel_id=ch.id,
                    content=content,
                    send_silent=False,
                    pin_after_send=True,
                    scheduler_category="verify_funnel",
                    created_at=datetime.now(timezone.utc),
                )
                db.add(sched)
                db.flush()
                report["status"] = "created"
                report["scheduler_id"] = sched.id
        else:
            report["scheduler_id"] = sched.id
            report["status"] = "would_update" if not args.execute else "updated"
            if args.execute:
                sched.content = content
                sched.pin_after_send = True
                sched.send_silent = False
                sched.scheduler_category = sched.scheduler_category or "verify_funnel"

        if args.execute:
            db.commit()
        else:
            db.rollback()

        print(json.dumps(report, indent=2, ensure_ascii=False))
    finally:
        db.close()


if __name__ == "__main__":
    main()
