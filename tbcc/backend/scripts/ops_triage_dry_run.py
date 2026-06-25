#!/usr/bin/env python3
"""
Dry-run the ops flywheel approve -> Cursor triage pipeline (no Telegram required).

  cd tbcc/backend && py -3.13 scripts/ops_triage_dry_run.py
  py -3.13 scripts/ops_triage_dry_run.py --run-agent   # full Cursor SDK call
"""
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


def main() -> int:
    parser = argparse.ArgumentParser(description="TBCC ops triage dry-run")
    parser.add_argument("--run-agent", action="store_true", help="Invoke Cursor SDK after approve")
    args = parser.parse_args()

    from app.services.admin_inbox import get_inbox_event_by_id, push_admin_inbox_event
    from app.services.cursor_triage import can_run_triage, triage_enabled
    from app.services.ops_flywheel import approve_action, list_pending, route_event

    if not triage_enabled():
        print(json.dumps({"ok": False, "error": "TBCC_CURSOR_TRIAGE_ENABLED=0 — restart backend after .env change"}))
        return 1

    event = push_admin_inbox_event(
        category="ops",
        severity="critical",
        title="[DRY-RUN] service_traceback in scheduled_post_service",
        body="sqlite3.OperationalError: database is locked (synthetic ops triage test)",
        meta={
            "code": "service_traceback",
            "dry_run": True,
            "service": "scheduled_post_service",
        },
        instant=False,
    )
    if not event:
        print(json.dumps({"ok": False, "error": "inbox disabled"}))
        return 1

    event_id = str(event["id"])
    routed = route_event(event, source="dry_run")
    pending_id = routed.get("pending_id")
    out: dict = {
        "ok": True,
        "event_id": event_id,
        "routed": routed,
        "pending_before_approve": list_pending(),
    }

    ok, reason = can_run_triage(get_inbox_event_by_id(event_id))
    out["can_agent"] = ok
    out["can_agent_reason"] = reason

    if not pending_id:
        print(json.dumps({**out, "error": "expected pending approval for service_traceback"}, indent=2))
        return 1

    if args.run_agent:
        approved = approve_action(str(pending_id))
        out["approved"] = approved
        if ok and not approved.get("cursor"):
            from app.services.cursor_triage import run_cursor_triage

            out["triage"] = run_cursor_triage(event_id, source="dry_run_approve")
    else:
        out["approve_hint"] = f"POST /ops/flywheel/approve/{pending_id} or Secretary Approve fix"
        out["pending_id"] = pending_id

    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
