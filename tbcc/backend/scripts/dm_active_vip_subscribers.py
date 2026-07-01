#!/usr/bin/env python3
"""DM active AOF VIP (group-access) subscribers their channel invite — one-time backfill."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill VIP welcome DMs to active subscribers")
    parser.add_argument("--execute", action="store_true", help="Send DMs (default: dry-run list only)")
    parser.add_argument("--limit", type=int, default=0, help="Max users (0 = all)")
    args = parser.parse_args()

    from app.database.session import SessionLocal
    from app.models.subscription import Subscription
    from app.models.subscription_plan import SubscriptionPlan
    from app.services.aof_growth_hub import resolve_group_access_plan_id
    from app.services.aof_vip_perks import is_group_access_plan
    from app.workers.vip_welcome_worker import send_vip_welcome_dm_sync

    db = SessionLocal()
    try:
        plan_id = resolve_group_access_plan_id(db)
        if not is_group_access_plan(db, plan_id):
            print(json.dumps({"ok": False, "error": "group_access_plan_not_found"}))
            return 1

        rows = (
            db.query(Subscription.telegram_user_id)
            .join(SubscriptionPlan, Subscription.plan_id == SubscriptionPlan.id)
            .filter(
                Subscription.status == "active",
                SubscriptionPlan.product_type == "subscription",
                SubscriptionPlan.bot_section == "main",
            )
            .distinct()
            .all()
        )
        user_ids = [int(r[0]) for r in rows]
        if args.limit > 0:
            user_ids = user_ids[: args.limit]

        report = {"ok": True, "execute": args.execute, "plan_id": plan_id, "users": len(user_ids), "results": []}
        for uid in user_ids:
            if not args.execute:
                report["results"].append({"telegram_user_id": uid, "status": "would_send"})
                continue
            out = send_vip_welcome_dm_sync(
                uid,
                plan_id,
                charge_id=f"backfill_{uid}",
                payment_method=None,
            )
            report["results"].append({"telegram_user_id": uid, **out})
    finally:
        db.close()

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
