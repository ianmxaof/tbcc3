"""Set/clear backend restart grace (suppresses ops toasts during expected API downtime)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_backend))
_dotenv = _backend.parent / ".env"
if _dotenv.is_file():
    for line in _dotenv.read_text(encoding="utf-8", errors="replace").splitlines():
        t = line.strip()
        if not t or t.startswith("#") or "=" not in t:
            continue
        k, _, v = t.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v

from app.services.ops_restart_grace import (  # noqa: E402
    clear_backend_restart_grace,
    mark_backend_restart_grace,
    restart_grace_public_snapshot,
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mark", action="store_true", help="Suppress ops toasts (before backend stop)")
    p.add_argument("--clear", action="store_true", help="End grace (optional --tail seconds after health OK)")
    p.add_argument("--seconds", type=int, default=0, help="Grace duration for --mark")
    p.add_argument("--tail", type=int, default=-1, help="Tail seconds for --clear (default from env)")
    p.add_argument("--status", action="store_true", help="Print current grace state")
    args = p.parse_args()

    if args.status or (not args.mark and not args.clear):
        print(restart_grace_public_snapshot())
        return 0
    if args.mark:
        sec = args.seconds if args.seconds > 0 else None
        print(mark_backend_restart_grace(seconds=sec))
        return 0
    tail = None if args.tail < 0 else args.tail
    print(clear_backend_restart_grace(tail_seconds=tail))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
