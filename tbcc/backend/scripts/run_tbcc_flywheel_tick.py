#!/usr/bin/env python3
"""
TBCC flywheel tick — ops routing + growth signals (internal cron; not GitHub OpenClaw).

  cd tbcc/backend && py -3.13 scripts/run_tbcc_flywheel_tick.py
  py -3.13 scripts/run_tbcc_flywheel_tick.py --dry-run

Prefer real OpenClaw (github.com/openclaw/openclaw) + TBCC MCP for autonomous ops.
See tbcc/docs/OPENCLAW_TBCC_INTEGRATION.md
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


def main() -> int:
    parser = argparse.ArgumentParser(description="TBCC flywheel tick (ops + growth)")
    parser.add_argument("--dry-run", action="store_true", help="Status only, no tick")
    parser.add_argument("--limit", type=int, default=1, help="Ops flywheel event limit")
    parser.add_argument("--growth-only", action="store_true")
    parser.add_argument("--ops-only", action="store_true")
    parser.add_argument("--no-refresh-views", action="store_true")
    args = parser.parse_args()

    import httpx

    base = (os.getenv("TBCC_API_URL") or "http://127.0.0.1:8000").rstrip("/")

    try:
        st = httpx.get(f"{base}/analytics/signals/status", timeout=8.0)
        sig_status = st.json() if st.status_code == 200 else {"ok": False, "note": f"HTTP {st.status_code}"}
        fw = httpx.get(f"{base}/ops/flywheel/status", timeout=8.0)
        fw.raise_for_status()
        flywheel_status = fw.json()
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"backend unreachable: {e}"}))
        return 1

    print(json.dumps({"signals": sig_status, "flywheel": flywheel_status}, indent=2))

    if args.dry_run:
        try:
            md = httpx.get(f"{base}/analytics/signals/markdown", timeout=15.0)
            if md.status_code == 200:
                print("\n--- signal preview ---\n")
                print(md.text)
        except Exception as e:
            print(json.dumps({"preview_error": str(e)}))
        return 0

    out: dict = {"ok": True}

    if args.growth_only:
        try:
            r = httpx.post(
                f"{base}/analytics/signals/tick",
                params={"refresh_views": "false" if args.no_refresh_views else "true"},
                timeout=120.0,
            )
            r.raise_for_status()
            out["growth"] = r.json()
        except Exception as e:
            out["growth"] = {"ok": False, "error": str(e)}
            out["ok"] = False
    elif args.ops_only:
        try:
            r = httpx.post(f"{base}/ops/flywheel/tick", json={"limit": args.limit}, timeout=30.0)
            r.raise_for_status()
            out["ops"] = r.json()
        except Exception as e:
            out["ops"] = {"ok": False, "error": str(e)}
            out["ok"] = False
    else:
        try:
            r = httpx.post(
                f"{base}/analytics/tbcc-flywheel/tick",
                params={"ops_limit": args.limit},
                timeout=120.0,
            )
            r.raise_for_status()
            out = r.json()
        except Exception as e:
            out = {"ok": False, "error": str(e)}

    print(json.dumps(out, indent=2))
    if out.get("growth", {}).get("markdown"):
        print("\n--- growth markdown ---\n")
        print(out["growth"]["markdown"])
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
