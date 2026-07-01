#!/usr/bin/env python3
"""Ensure AOF VIP channel (+ optional pool) exists in TBCC DB."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.data.aof_network import AOF_VIP_IDENT, AOF_VIP_INVITE_PRIMARY, AOF_VIP_POOL_NAME
from app.models.channel import Channel
from app.models.content_pool import ContentPool


def main() -> int:
    parser = argparse.ArgumentParser(description="Register AOF VIP channel in TBCC")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    report: dict = {"channel_ident": AOF_VIP_IDENT, "invite": AOF_VIP_INVITE_PRIMARY}
    try:
        ch = db.query(Channel).filter(Channel.identifier == AOF_VIP_IDENT).first()
        if ch:
            report["channel"] = {"id": ch.id, "status": "exists"}
            if args.execute:
                ch.name = "AOF VIP"
                ch.invite_link = AOF_VIP_INVITE_PRIMARY
        else:
            report["channel"] = {"status": "would_create" if not args.execute else "created"}
            if args.execute:
                ch = Channel(name="AOF VIP", identifier=AOF_VIP_IDENT, invite_link=AOF_VIP_INVITE_PRIMARY)
                db.add(ch)
                db.flush()
                report["channel"]["id"] = ch.id

        pool = db.query(ContentPool).filter(ContentPool.name == AOF_VIP_POOL_NAME).first()
        if pool:
            report["pool"] = {"id": pool.id, "status": "exists"}
        else:
            report["pool"] = {"status": "would_create" if not args.execute else "created"}
            if args.execute and ch:
                pool = ContentPool(
                    name=AOF_VIP_POOL_NAME,
                    channel_id=ch.id,
                    album_size=1,
                    interval_minutes=0,
                    auto_post_enabled=False,
                    randomize_queue=True,
                )
                db.add(pool)
                db.flush()
                report["pool"]["id"] = pool.id

        if args.execute:
            db.commit()
            from app.services.aof_vip_fulfillment import wire_group_access_plan_to_vip_channel

            report["plan_wire"] = wire_group_access_plan_to_vip_channel(db, execute=True)
        else:
            db.rollback()
            from app.services.aof_vip_fulfillment import wire_group_access_plan_to_vip_channel

            report["plan_wire"] = wire_group_access_plan_to_vip_channel(db, execute=False)
    finally:
        db.close()

    report["note"] = "VIP is separate from addlist — paid Stars lane only."
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
