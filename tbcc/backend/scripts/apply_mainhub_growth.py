"""
Seed @aofmainhub (AOF LINK HUB) schedulers: durable VIP CTA + ephemeral pin liveness.

  cd tbcc/backend
  py -3.13 scripts/apply_mainhub_growth.py              # preview
  py -3.13 scripts/apply_mainhub_growth.py --execute
  py -3.13 scripts/apply_mainhub_growth.py --execute --post-now
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
from app.services.mainhub_growth import apply_mainhub_growth


def main() -> None:
    p = argparse.ArgumentParser(description="Apply @aofmainhub CTA + liveness schedulers")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--post-now", action="store_true", help="Queue immediate send for mainhub schedulers")
    args = p.parse_args()
    db = SessionLocal()
    try:
        report = apply_mainhub_growth(db, execute=args.execute, post_now=args.post_now)
        if args.execute:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
