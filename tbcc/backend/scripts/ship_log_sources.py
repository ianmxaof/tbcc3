"""Print git + improvement-notes context for TBCC Ship Log protocol. Run from tbcc/backend."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
env_path = ROOT / ".env"
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ship_log_sources import collect_ship_log_context, format_ship_log_context


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="TBCC ship log — gather sources")
    p.add_argument("--since", default="7 days ago", help='Git --since value (default: "7 days ago")')
    p.add_argument("--max-commits", type=int, default=25)
    args = p.parse_args()
    ctx = collect_ship_log_context(since=args.since, max_commits=args.max_commits)
    print(format_ship_log_context(ctx))


if __name__ == "__main__":
    main()
