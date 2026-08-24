#!/usr/bin/env python3
"""Grandfather dry-run for the AOF Library twin ("Archive of Filth", Phase 3 of
loot-forum-twin-week1). Counts active main-section VIP/subscribers who would be
auto-seated into the twin at cutover/beta, and prints an invite plan using the
twin's registered invite link.

DO NOT EXECUTE — this script is read-only. It issues zero Telegram Bot API
calls (no addChatMember, no createChatInviteLink, no DMs) and writes nothing
to the database. It only queries `subscriptions` / `subscription_plans` and
prints a plan. There is no --execute flag because there is nothing to
execute this phase; sending grandfather invites is a separate, later,
operator-approved track.

Population filter mirrors app.services.subscription_access.user_has_active_subscription
(subscriptions_only=True, bot_section="main") — the same "existing VIP /
main-section" population the placement doctrine already uses elsewhere
(vip_member_status.py, dm_active_vip_subscribers.py). Not a new SKU.

  py -3.13 scripts/grandfather_dry_run_aof_library.py

See tbcc/docs/handoffs/2026-08-22_loot-forum-twin-week1.md (Phase 3) and
tbcc/docs/handoffs/2026-08-22_loot-forum-twin-week1_report.md.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.aof_library_forum import (
    aof_library_forum_display_name,
    aof_library_forum_ident,
    aof_library_forum_invite,
)
from app.database.session import SessionLocal
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan


def main() -> None:
    ident = aof_library_forum_ident()
    invite = aof_library_forum_invite()
    display_name = aof_library_forum_display_name()

    db = SessionLocal()
    try:
        now = datetime.utcnow()
        rows = (
            db.query(Subscription, SubscriptionPlan)
            .join(SubscriptionPlan, Subscription.plan_id == SubscriptionPlan.id)
            .filter(
                Subscription.status == "active",
                SubscriptionPlan.product_type == "subscription",
                SubscriptionPlan.bot_section == "main",
            )
            .all()
        )

        # Belt-and-suspenders expiry check (same guard as
        # subscription_access._active_rows) in case a row's status hasn't
        # been flipped to "expired" by the worker yet.
        active: list[tuple[Subscription, SubscriptionPlan]] = []
        for sub, plan in rows:
            exp = sub.expires_at
            if exp is None or exp > now:
                active.append((sub, plan))

        by_user: dict[int, tuple[Subscription, SubscriptionPlan]] = {}
        for sub, plan in active:
            uid = int(sub.telegram_user_id)
            # A user could hold >1 active main-section row; keep any one —
            # this is a seat headcount, not a per-subscription ledger.
            by_user.setdefault(uid, (sub, plan))

        plan_breakdown = Counter(plan.name for _sub, plan in by_user.values())
        payment_breakdown = Counter((sub.payment_method or "unknown") for sub, _plan in by_user.values())

        report = {
            "ok": True,
            "generated_at": now.isoformat() + "Z",
            "do_not_execute": True,
            "population": "active main-section subscriptions (subscription_access.user_has_active_subscription, bot_section='main')",
            "grandfather_count": len(by_user),
            "plan_breakdown": dict(plan_breakdown),
            "payment_method_breakdown": dict(payment_breakdown),
            "twin": {
                "display_name": display_name,
                "ident": ident,
                "invite": invite,
            },
            "invite_plan": (
                f"{len(by_user)} people x twin invite {invite} "
                f"({display_name} {ident}) — PLAN TEXT ONLY, no sends issued by this script"
            ),
        }
    finally:
        db.close()

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("\nDry-run only — zero Telegram invite/DM calls made. No --execute flag exists this phase.")


if __name__ == "__main__":
    main()
