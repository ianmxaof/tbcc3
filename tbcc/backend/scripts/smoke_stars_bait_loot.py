"""
Smoke Stars bait loot handoff — plan wiring + deep links (no Telegram send).

  cd tbcc/backend
  py -3 scripts/smoke_stars_bait_loot.py
  py -3 scripts/smoke_stars_bait_loot.py --api https://api.powercore.app
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()


def _fetch_plans(api_base: str) -> list[dict]:
    import httpx

    url = f"{api_base.rstrip('/')}/subscription-plans/"
    resp = httpx.get(url, timeout=20.0)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else data.get("items", [])


def main() -> None:
    p = argparse.ArgumentParser(description="Smoke Stars bait loot wiring")
    p.add_argument("--api", default="https://api.powercore.app", help="TBCC API base URL")
    args = p.parse_args()

    from app.services.stars_bait_copy import (
        StarsBaitProduct,
        checkout_start_payload,
        parse_bait_start_payload,
        _payment_bot_username,
    )

    assert parse_bait_start_payload("bait_loot") is StarsBaitProduct.LOOT_KEY

    plans = _fetch_plans(args.api)
    loot = next(
        (
            x
            for x in plans
            if (x.get("bot_section") or "").lower() == "loot"
            and x.get("is_active", True)
            and int(x.get("price_stars") or 0) > 0
        ),
        None,
    )
    if not loot:
        raise SystemExit("FAIL: no active loot plan with Stars price on API")

    plan_ids = {
        "loot_key": int(loot["id"]),
        "day_pass": next(
            (
                int(x["id"])
                for x in plans
                if "lane pass" in (x.get("name") or "").lower() and x.get("is_active", True)
            ),
            None,
        ),
        "subscription": next(
            (
                int(x["id"])
                for x in plans
                if (x.get("bot_section") or "").lower() == "main"
                and int(x.get("price_stars") or 0) > 0
                and x.get("is_active", True)
            ),
            None,
        ),
    }
    checkout = checkout_start_payload(StarsBaitProduct.LOOT_KEY, plan_ids)
    pay = _payment_bot_username()

    report = {
        "ok": True,
        "api": args.api,
        "payment_bot": pay,
        "loot_plan": {
            "id": loot.get("id"),
            "name": loot.get("name"),
            "price_stars": loot.get("price_stars"),
        },
        "checkout_payload": checkout,
        "smoke_url": f"https://t.me/{pay}?start=bait_loot",
        "direct_checkout_url": f"https://t.me/{pay}?start={checkout}",
        "operator_checklist": [
            "Open smoke_url in Telegram — expect bait hook + 2 buttons",
            "Tap primary CTA — should loop bait_loot or hand off",
            f"Tap 'Subscribe — Stars' row — expect cm{plan_ids['loot_key']} checkout menu",
            "Complete Stars invoice smoke (optional) — 150⭐ Loot Room key",
        ],
    }
    print(json.dumps(report, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
