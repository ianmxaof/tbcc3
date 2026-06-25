#!/usr/bin/env python3
"""
Local substitute for Cursor Automation "TBCC critical ops triage".

Polls ops alerts, routes flywheel tick, dumps focus + triage status.
When critical alerts exist and TBCC_CURSOR_OPS_AUTOMATION_AGENT=1, invokes cursor-sdk.

  cd tbcc/backend && py -3.13 scripts/run_cursor_ops_automation_tick.py
  py -3.13 scripts/run_cursor_ops_automation_tick.py --agent   # invoke Cursor SDK on first alert
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parents[1]
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from dotenv import load_dotenv

_env = _backend.parent / ".env"
if _env.exists():
    load_dotenv(_env, override=True)


CRITICAL_CODES = frozenset(
    {
        "session_lock_storm",
        "session_sqlite_lock",
        "worker_crash",
        "api_port_duplicate",
        "uvicorn_orphans",
        "service_traceback",
        "redis_down",
    }
)


def main() -> int:
    parser = argparse.ArgumentParser(description="TBCC Cursor ops automation tick")
    parser.add_argument("--agent", action="store_true", help="Run cursor-sdk triage when alert has event_id")
    args = parser.parse_args()
    run_agent = args.agent or (
        os.getenv("TBCC_CURSOR_OPS_AUTOMATION_AGENT") or "0"
    ).strip().lower() in ("1", "true", "yes", "on")

    import httpx

    base = (os.getenv("TBCC_API_URL") or "http://127.0.0.1:8000").rstrip("/")
    report: dict = {"ok": True, "base": base}

    try:
        poll = httpx.get(f"{base}/ops/alerts/poll", timeout=10.0)
        poll.raise_for_status()
        alerts = poll.json().get("alerts") or []
        report["alerts_count"] = len(alerts)
        critical = [
            a
            for a in alerts
            if str(a.get("severity") or "").lower() == "critical"
            and str(a.get("code") or "") in CRITICAL_CODES
        ]
        report["critical"] = [{"code": a.get("code"), "title": a.get("title")} for a in critical[:3]]

        if not critical:
            print(json.dumps({**report, "message": "no new critical alerts"}, indent=2))
            return 0

        tick = httpx.post(f"{base}/ops/flywheel/tick", json={"limit": 1}, timeout=30.0)
        tick.raise_for_status()
        report["flywheel"] = tick.json()

        focus = httpx.get(f"{base}/ops/focus", timeout=10.0)
        report["focus"] = focus.json() if focus.status_code == 200 else {"error": focus.status_code}

        triage_st = httpx.get(f"{base}/ops/triage/status", timeout=10.0)
        report["triage_status"] = triage_st.json() if triage_st.status_code == 200 else {"error": triage_st.status_code}

        if run_agent and triage_st.status_code == 200 and triage_st.json().get("enabled"):
            event_id = None
            for item in report.get("flywheel", {}).get("processed") or []:
                event_id = item.get("event_id") or (
                    (item.get("cursor") or {}).get("event_id")
                )
                if event_id:
                    break
            if not event_id:
                from app.services.admin_inbox import list_inbox_events

                for ev in list_inbox_events(limit=5, category="ops", min_severity="critical"):
                    code = (ev.get("meta") or {}).get("code")
                    if code in CRITICAL_CODES:
                        event_id = ev.get("id")
                        break
            if event_id:
                tr = httpx.post(
                    f"{base}/ops/triage/run",
                    json={"event_id": event_id, "source": "automation_tick"},
                    timeout=600.0,
                )
                report["triage_run"] = tr.json() if tr.status_code == 200 else {"error": tr.status_code, "body": tr.text[:500]}

        print(json.dumps(report, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e), **report}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
