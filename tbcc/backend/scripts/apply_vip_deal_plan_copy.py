#!/usr/bin/env python3
"""Write AOF VIP deal-seller copy onto the group-access subscription plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.services.aof_vip_deal_copy import sync_plan_deal_descriptions


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync VIP deal copy to subscription_plans row")
    parser.add_argument("--execute", action="store_true", help="Write DB (default: preview)")
    parser.add_argument("--plan-id", type=int, default=0, help="Override plan id")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if not args.execute:
            from app.services.aof_growth_hub import resolve_group_access_plan_id
            from app.services.aof_vip_deal_copy import (
                build_vip_deal_caption_html,
                plan_description_variations,
                plan_invoice_description_short,
            )

            pid = int(args.plan_id or resolve_group_access_plan_id(db))
            preview = {
                "plan_id": pid,
                "invoice_description": plan_invoice_description_short(db),
                "variations": plan_description_variations(),
                "checkout_caption_preview": build_vip_deal_caption_html(db, pid),
            }
            print(json.dumps(preview, indent=2, ensure_ascii=False))
            return 0
        result = sync_plan_deal_descriptions(db, plan_id=args.plan_id or None)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
