#!/usr/bin/env python3
"""
Micro-pull from SCRP folder sources into a Storage Hub forum subtopic.

  cd tbcc/backend
  py -3.13 scripts/run_scrape_micro_pull.py --lane ass
  py -3.13 scripts/run_scrape_micro_pull.py --lane ass --execute --limit 10

Requires admin.session. Pilot default lane: ass (AOF ASS STORAGE).
Set TBCC_SCRAPE_MICRO_PULL_ENABLED=1 for Beat/Celery tick.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.services.scrape_micro_pull import (
    MICRO_PULL_PILOT_LANE,
    plan_lane_micro_pull,
    run_lane_micro_pull,
)
from app.services.telegram_admin import run_telegram_io


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="SCRP micro-pull → Storage Hub subtopic")
    p.add_argument("--lane", default=MICRO_PULL_PILOT_LANE, help="AOF lane key (default: ass)")
    p.add_argument("--limit", type=int, default=None, help="Max messages per source (default: env or 10)")
    p.add_argument("--execute", action="store_true", help="Run pull (default: plan preview only)")
    args = p.parse_args()

    with SessionLocal() as db:
        plan = plan_lane_micro_pull(db, args.lane.strip().lower())

    if not args.execute:
        plan["status"] = "preview — pass --execute to run"
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0 if plan.get("ok") else 1

    async def _run(storage):
        with SessionLocal() as db:
            return await run_lane_micro_pull(
                storage,
                db,
                args.lane.strip().lower(),
                limit=args.limit,
            )

    try:
        result = asyncio.run(run_telegram_io(_run))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)[:500], **plan}, indent=2, ensure_ascii=False))
        return 1

    out = {"ok": True, **result}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    fwd = int(result.get("forwarded", 0) or 0)
    upl = int(result.get("uploaded", 0) or 0)
    return 0 if fwd + upl > 0 or result.get("executed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
