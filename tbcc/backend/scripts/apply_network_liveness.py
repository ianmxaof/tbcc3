"""
Apply AOF network liveness automation (faster cadences, pulse posts, drop signals).

  cd tbcc/backend
  py -3.13 scripts/apply_network_liveness.py              # preview
  py -3.13 scripts/apply_network_liveness.py --execute
  py -3.13 scripts/apply_network_liveness.py --execute --celebrate-first-sub
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
from app.services.aof_network_liveness import (
    apply_network_liveness,
    queue_first_subscription_celebration,
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="AOF network liveness automation")
    p.add_argument("--execute", action="store_true", help="Apply changes (default: preview)")
    p.add_argument(
        "--celebrate-first-sub",
        action="store_true",
        help="Queue one-shot main-group post for first Stars subscription",
    )
    p.add_argument("--force-celebration", action="store_true", help="Re-post celebration even if already sent")
    args = p.parse_args()

    db = SessionLocal()
    try:
        report = apply_network_liveness(db, execute=args.execute)
        if args.celebrate_first_sub and args.execute:
            report["celebration"] = queue_first_subscription_celebration(
                db, force=args.force_celebration
            )
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    finally:
        db.close()


if __name__ == "__main__":
    main()
