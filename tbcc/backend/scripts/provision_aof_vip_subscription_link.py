#!/usr/bin/env python3
"""
Create (or preview) Telegram Stars subscription invite link for AOF VIP broadcast channel.

Requires @aofsubscriptions_bot (BOT_TOKEN) as channel admin with can_invite_users.

  cd tbcc/backend
  py -3.13 scripts/provision_aof_vip_subscription_link.py
  py -3.13 scripts/provision_aof_vip_subscription_link.py --execute
  py -3.13 scripts/provision_aof_vip_subscription_link.py --execute --stars 500
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.services.aof_growth_hub import resolve_group_access_plan_id
from app.services.aof_vip_checkout import (
    create_vip_subscription_invite_link,
    vip_channel_ident,
    vip_primary_invite_url,
    vip_subscription_invite_url,
)
from app.models.subscription_plan import SubscriptionPlan


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision AOF VIP Stars subscription invite link")
    parser.add_argument("--execute", action="store_true", help="Call Telegram Bot API (default: preview)")
    parser.add_argument("--stars", type=int, default=0, help="Override Stars price (default: group-access plan)")
    parser.add_argument("--name", default="AOF VIP — network checkout", help="Invite link label (max 32 chars)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        plan_id = resolve_group_access_plan_id(db)
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
        stars = int(args.stars or (plan.price_stars if plan else 0) or 500)
    finally:
        db.close()

    report = {
        "channel_id": vip_channel_ident(),
        "primary_admin_invite": vip_primary_invite_url(),
        "existing_subscription_invite": vip_subscription_invite_url() or None,
        "plan_id": plan_id,
        "subscription_price_stars": stars,
        "subscription_period_seconds": 2_592_000,
        "note": (
            "Regular admin invites (unlimited / 1-day / 1-use) are NOT Stars checkout links. "
            "Run with --execute to create createChatSubscriptionInviteLink via the payment bot."
        ),
    }

    if not args.execute:
        report["status"] = "preview"
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    result = create_vip_subscription_invite_link(subscription_price=stars, name=args.name)
    report["telegram"] = result
    if result.get("ok"):
        report["status"] = "created"
        link = result.get("invite_link")
        report["env_append"] = f"TBCC_AOF_VIP_SUBSCRIPTION_INVITE_URL={link}"
        print(json.dumps(report, indent=2, ensure_ascii=False))
        print("\nAdd to tbcc/.env:\n" + report["env_append"])
        return 0

    report["status"] = "failed"
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
