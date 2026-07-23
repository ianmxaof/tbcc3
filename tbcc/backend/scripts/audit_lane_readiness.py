"""
Audit approved photo/video depth per AOF lane vs Loot Room subtopic readiness.

  cd tbcc/backend && py -3.13 scripts/audit_lane_readiness.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.services.lane_readiness import audit_lane_readiness


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    db = SessionLocal()
    try:
        report = audit_lane_readiness(db)
    finally:
        db.close()
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
