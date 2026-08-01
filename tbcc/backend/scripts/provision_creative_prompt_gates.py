#!/usr/bin/env python3
"""Queue LV provision for all pending prompt_gate rows from creative catalog ingest."""

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

from app.database.session import SessionLocal
from app.models.prompt_gate import PROMPT_GATE_STATUS_PENDING, PromptGate
from app.services.prompt_gate_registry import list_provision_queue


def main() -> int:
    parser = argparse.ArgumentParser(description="List or run prompt_gate LV provision batch")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true", help="Run provision_prompt_gates --execute")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        pending = (
            db.query(PromptGate)
            .filter(PromptGate.status == PROMPT_GATE_STATUS_PENDING)
            .order_by(PromptGate.id.asc())
            .limit(max(1, args.limit))
            .count()
        )
        work = list_provision_queue(db, limit=args.limit)
        report = {
            "ok": True,
            "pending_count": pending,
            "work_items": len(work),
            "keys": [w.row.key for w in work[:20]],
        }
        if args.execute:
            from scripts.provision_prompt_gates import main as provision_main

            sys.argv = ["provision_prompt_gates.py", "--execute", "--limit", str(args.limit)]
            provision_main()
            report["provision"] = "delegated"
        print(json.dumps(report, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
