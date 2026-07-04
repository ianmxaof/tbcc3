#!/usr/bin/env python3
"""Smoke-test AOF VIP subscription link + post checkout button merge."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

import httpx

from app.database.session import SessionLocal
from app.services.aof_growth_hub import resolve_group_access_plan_id
from app.services.aof_vip_checkout import (
    merge_checkout_buttons,
    use_vip_star_subscription,
    vip_channel_ident,
    vip_subscription_invite_url,
)


def main() -> int:
    report: dict = {
        "vip_channel": vip_channel_ident(),
        "use_vip_subscription": use_vip_star_subscription(),
        "subscription_invite": vip_subscription_invite_url() or None,
    }

    token = (__import__("os").getenv("BOT_TOKEN") or "").strip()
    sub_url = vip_subscription_invite_url()
    if token and sub_url:
        try:
            with httpx.Client(timeout=20.0) as client:
                r = client.get(
                    f"https://api.telegram.org/bot{token}/getChat",
                    params={"chat_id": vip_channel_ident()},
                )
                report["getChat"] = r.json()
        except Exception as e:
            report["getChat_error"] = str(e)

    db = SessionLocal()
    try:
        plan_id = resolve_group_access_plan_id(db)
        buttons = merge_checkout_buttons(
            [],
            db,
            checkout_stars_enabled=True,
            checkout_stars_plan_id=plan_id,
        )
        report["plan_id"] = plan_id
        report["checkout_buttons"] = buttons
    finally:
        db.close()

    ok = bool(report.get("subscription_invite")) and len(report.get("checkout_buttons") or []) >= 1
    report["ok"] = ok
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
