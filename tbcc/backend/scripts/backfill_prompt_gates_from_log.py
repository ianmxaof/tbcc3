#!/usr/bin/env python3
"""Apply LV slugs from 2026-08-01 headed provision log (no Playwright)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

# Queue order from provision batch + Created slug: lines (terminal 621433).
# Skipped: loot_card_tier-08 (DNS), he_coming_filmstrip_5x (wizard timeout).
LOG_BACKFILL: dict[str, str] = {
    "loot_card_tier-02": "https://link-target.net/1367336/N4zw1UvyMQN7",
    "loot_card_tier-03": "https://link-target.net/1367336/axkyh0zdOUkX",
    "loot_card_tier-04": "https://link-target.net/1367336/aKatKr6sDP7W",
    "loot_card_tier-05": "https://link-target.net/1367336/UdINg30ScN5z",
    "loot_card_tier-06": "https://link-target.net/1367336/Bhga48uDbA7r",
    "loot_card_tier-07": "https://link-target.net/1367336/SVZG4DGcwVNS",
    "loot_card_tier-09": "https://link-target.net/1367336/Zezl4Y5DJq3X",
    "loot_card_tier-10": "https://link-target.net/1367336/oZtmIZEAX19X",
    "promo_martyrs-ma07-10": "https://link-target.net/1367336/fJklR2PSCR4s",
    "promo_martyrs-grid-classic": "https://link-target.net/1367336/iECUDoCVzuYC",
    "promo_martyrs-single-breakfast": "https://link-target.net/1367336/4aXqxcixbfnu",
    "promo_scene_ma-01": "https://link-target.net/1367336/kr3huOaSdXUH",
    "promo_scene_ma-02": "https://link-target.net/1367336/zJikOBHx6wlV",
    "promo_scene_ma-03": "https://link-target.net/1367336/ZNmOxa1DKS2K",
    "promo_scene_ma-04": "https://link-target.net/1367336/YUd5nwi3R7Yh",
    "promo_scene_ma-05": "https://link-target.net/1367336/Fsmj7PHsTmA3",
    "promo_scene_ma-06": "https://link-target.net/1367336/XUKmlqy71XNj",
    "promo_scene_ma-07": "https://link-target.net/1367336/8ns3m9ZMkoMl",
    "promo_scene_ma-08": "https://link-target.net/1367336/5Ba8VM4Eny9R",
    "promo_scene_ma-09": "https://link-target.net/1367336/ocdXEQsKUNUU",
    "promo_scene_ma-10": "https://link-target.net/1367336/mVpHlmvr7eDS",
    "he_coming_discovery": "https://link-target.net/1367336/LCMb5qOGSxgQ",
    "he_coming_session_logs": "https://link-target.net/1367336/w1n0g5RuPVAo",
    "he_coming_window_feed": "https://link-target.net/1367336/0T7RVgyEEoI0",
    "he_coming_closet_feed": "https://link-target.net/1367336/2BjimnYkavdb",
    "he_coming_backseat": "https://link-target.net/1367336/73YDIKKGXRKM",
    "jackal_tapes_interview": "https://link-target.net/1367336/fV5XoDBrjF1X",
    "jackal_tapes_break_the_man": "https://link-target.net/1367336/G0YGC7OPqkMu",
    "jackal_tapes_war_is_home": "https://link-target.net/1367336/Ktr9dYMXlyFw",
    "jackal_tapes_mikes_bar": "https://link-target.net/1367336/bb6dpUZsFqZ8",
    "jackal_tapes_monster_display": "https://link-target.net/1367336/3yzuxAhCKUhT",
    "jackal_tapes_filmstrip_5x": "https://link-target.net/1367336/Jt5ylGVynqIU",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill prompt_gates from provision log slugs")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    from app.database.session import SessionLocal
    from app.models.prompt_gate import PROMPT_GATE_STATUS_PENDING, PROMPT_GATE_STATUS_PROVISIONED, PromptGate
    from app.services.prompt_gate_registry import apply_provision_success

    report: dict = {"ok": True, "execute": args.execute, "applied": [], "skipped": [], "missing": []}
    db = SessionLocal()
    try:
        for key, url in LOG_BACKFILL.items():
            row = (
                db.query(PromptGate)
                .filter(PromptGate.key == key)
                .order_by(PromptGate.id.desc())
                .first()
            )
            if not row:
                report["missing"].append(key)
                continue
            if row.status == PROMPT_GATE_STATUS_PROVISIONED and (row.lv_url or "").strip() == url:
                report["skipped"].append({"key": key, "reason": "already_provisioned"})
                continue
            if row.status not in (PROMPT_GATE_STATUS_PENDING, "failed"):
                report["skipped"].append({"key": key, "reason": f"status={row.status}"})
                continue
            if args.execute:
                apply_provision_success(db, row, url, probe={"flags": ["LV_SHELL", "LOG_BACKFILL"]})
            report["applied"].append({"key": key, "url": url, "id": row.id})
        if not args.execute:
            db.rollback()
        print(json.dumps(report, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
