"""Print git + improvement-notes context for TBCC Ship Log protocol. Run from tbcc/backend."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.services.ship_log_sources import collect_ship_log_context, format_ship_log_context, write_ship_log_cache


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="TBCC ship log — gather sources")
    p.add_argument("--since", default="7 days ago", help='Git --since value (default: "7 days ago")')
    p.add_argument("--max-commits", type=int, default=25)
    p.add_argument("--write-cache", action="store_true", help="Write .tbcc-run/ship_log_context.json for island")
    args = p.parse_args()
    if args.write_cache:
        path = write_ship_log_cache(since=args.since, max_commits=args.max_commits)
        print(path)
        return
    ctx = collect_ship_log_context(since=args.since, max_commits=args.max_commits)
    print(format_ship_log_context(ctx))


if __name__ == "__main__":
    main()
