#!/usr/bin/env python3
"""Queue pinned AOF VIP deal-seller post on main group (checkout enabled)."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.aof_network import MAIN_GROUP_IDENT
from app.database.session import SessionLocal
from app.models.channel import Channel
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.aof_growth_hub import queue_post_scheduler, resolve_group_access_plan_id
from app.services.aof_vip_deal_copy import build_vip_deal_caption_html

VIP_DEAL_SELL_NAME = "AOF VIP — Hall Pass deal seller"


def main() -> int:
    parser = argparse.ArgumentParser(description="Queue VIP deal-seller post on main group")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--pin", action="store_true", help="Pin after send")
    parser.add_argument("--force", action="store_true", help="Re-queue even if already sent")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        main_ch = db.query(Channel).filter(Channel.identifier == MAIN_GROUP_IDENT).first()
        if not main_ch:
            print("main group channel not in DB — run ensure scripts first", file=sys.stderr)
            return 1
        plan_id = resolve_group_access_plan_id(db)
        body = build_vip_deal_caption_html(db, plan_id, include_urgency=True)
        sched = (
            db.query(ScheduledTextPost)
            .filter(
                ScheduledTextPost.channel_id == main_ch.id,
                ScheduledTextPost.name == VIP_DEAL_SELL_NAME,
            )
            .first()
        )
        if sched and sched.sent_at and not args.force:
            print(f"Already sent post_id={sched.id} — pass --force to re-queue")
            return 0
        if not args.execute:
            print("DRY-RUN caption preview:\n")
            print(body[:1200])
            if len(body) > 1200:
                print("\n…")
            print(f"\nWould queue on channel {main_ch.name} plan_id={plan_id} checkout_stars_plan_id={plan_id}")
            return 0
        if not sched:
            sched = ScheduledTextPost(
                name=VIP_DEAL_SELL_NAME,
                channel_id=main_ch.id,
                content=body,
                send_silent=False,
                pin_after_send=bool(args.pin),
                checkout_stars_enabled=True,
                checkout_stars_plan_id=int(plan_id),
                created_at=datetime.now(timezone.utc),
            )
            db.add(sched)
            db.flush()
        else:
            sched.content = body
            sched.sent_at = None
            sched.checkout_stars_enabled = True
            sched.checkout_stars_plan_id = int(plan_id)
            sched.pin_after_send = bool(args.pin)
        db.commit()
        q = queue_post_scheduler(int(sched.id), countdown=0)
        print({"ok": True, "post_id": sched.id, **q})
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
