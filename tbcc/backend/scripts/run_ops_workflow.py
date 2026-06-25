#!/usr/bin/env python3
"""Run tbcc_ops_turn workflow (health → scheduling → flywheel → handoff)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parents[1]
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from dotenv import load_dotenv

_env = _backend.parent / ".env"
if _env.exists():
    load_dotenv(_env, override=True)

from app.services.ops_workflow_runner import run_ops_workflow, workflow_status  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="TBCC ops workflow runner")
    p.add_argument("--ops-limit", type=int, default=1)
    p.add_argument("--operator", default="openclaw")
    p.add_argument("--no-handoff", action="store_true")
    p.add_argument("--status", action="store_true")
    args = p.parse_args()

    if args.status:
        print(json.dumps(workflow_status(), indent=2))
        return 0

    out = run_ops_workflow(
        ops_limit=args.ops_limit,
        operator=args.operator,
        include_handoff=not args.no_handoff,
    )
    print(json.dumps(out, indent=2, default=str))
    handoff = (out.get("state") or {}).get("handoff_markdown")
    if handoff:
        print("\n--- handoff ---\n")
        print(handoff)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
