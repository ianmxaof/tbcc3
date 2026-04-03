"""
Queue a landing bulletin task (optionally force-send regardless of UTC hour).

Usage (from tbcc/backend):
  python scripts/trigger_landing_bulletin.py
  python scripts/trigger_landing_bulletin.py --force
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from app.workers.landing_bulletin_worker import send_aof_landing_bulletin


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--force",
        action="store_true",
        help="Send now even if current UTC hour != configured hour",
    )
    args = p.parse_args()
    r = send_aof_landing_bulletin.delay(force=args.force)
    print(f"Queued task id: {r.id}")


if __name__ == "__main__":
    main()
