#!/usr/bin/env python3
"""On-demand analytics direction — JSON or markdown for /analytics-direction protocol."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.services.analytics_direction import build_analytics_direction_report


def main() -> int:
    parser = argparse.ArgumentParser(description="TBCC analytics direction snapshot")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--markdown", action="store_true", help="Print markdown only")
    parser.add_argument("--use-llm", action="store_true", help="Append LLM narrative paragraph")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report = build_analytics_direction_report(db, days=args.days, use_llm=args.use_llm)
        if args.markdown:
            print(report.get("markdown") or "")
        else:
            payload = {k: v for k, v in report.items() if k != "markdown"}
            print(json.dumps(payload, indent=2, ensure_ascii=False))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
