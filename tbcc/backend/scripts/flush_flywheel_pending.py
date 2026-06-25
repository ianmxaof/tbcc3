#!/usr/bin/env python3
"""Bulk-reject stale flywheel pending actions (clears Secretary approval backlog)."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_backend = Path(__file__).resolve().parents[1]
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from dotenv import load_dotenv

_env = _backend.parent / ".env"
if _env.exists():
    load_dotenv(_env, override=True)


def main() -> int:
    p = argparse.ArgumentParser(description="Reject flywheel pending actions")
    p.add_argument("--all", action="store_true", help="Reject every pending action")
    p.add_argument("--older-than-days", type=int, default=0, help="Reject if created N+ days ago")
    p.add_argument("--code", action="append", help="Only reject matching alert code (repeatable)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    from app.services.ops_flywheel import list_pending, reject_action

    pending = list_pending()
    if not pending:
        print("No pending flywheel actions.")
        return 0

    codes = {c.strip() for c in (args.code or []) if c.strip()}
    now = datetime.now(timezone.utc)
    rejected: list[str] = []

    for action in pending:
        aid = str(action.get("id") or "")
        code = str(action.get("code") or "")
        created_raw = str(action.get("created") or "")
        if codes and code not in codes:
            continue
        if args.older_than_days > 0 and created_raw:
            try:
                created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                age_days = (now - created).total_seconds() / 86400
                if age_days < args.older_than_days:
                    continue
            except ValueError:
                pass
        elif not args.all and not codes and args.older_than_days <= 0:
            print("Specify --all, --older-than-days N, or --code ...")
            return 1
        if args.dry_run:
            print(f"would reject {aid} code={code} created={created_raw}")
        else:
            reject_action(aid)
            print(f"rejected {aid} code={code}")
        rejected.append(aid)

    print(f"Done: {len(rejected)} action(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
