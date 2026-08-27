#!/usr/bin/env python3
"""Readonly silent-fail probes — print ok|stale|never_seen|idle|blocked (exit 0).

Usage (from tbcc/backend):

  py -3.13 scripts/silent_fail_probe.py intake --lane inbox
  py -3.13 scripts/silent_fail_probe.py intake --all
  py -3.13 scripts/silent_fail_probe.py r2-export
  py -3.13 scripts/silent_fail_probe.py enrich-backlog
  py -3.13 scripts/silent_fail_probe.py all

No bot Start, no restarts. Requires REDIS_URL for intake; DATABASE_URL for r2-export.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _bootstrap() -> None:
    backend = Path(__file__).resolve().parents[1]
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))


def _print_result(payload: dict[str, Any], *, as_json: bool) -> int:
    verdict = str(payload.get("verdict") or "blocked")
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, default=str))
    else:
        # First token is the machine verdict for scripting /silent-fail external stops.
        print(verdict)
        mid = payload.get("id") or payload.get("lane_key") or ""
        evidence = payload.get("stop_evidence") or payload.get("error") or ""
        if mid or evidence:
            print(f"# {mid} {evidence}".strip())
        if payload.get("lanes"):
            for row in payload["lanes"]:
                print(
                    f"# lane={row.get('lane_key')} {row.get('verdict')} "
                    f"last_run_ts={row.get('last_run_ts')}"
                )
    return 0


def cmd_intake(args: argparse.Namespace) -> int:
    from app.services.silent_fail_probes import probe_intake_all, probe_intake_lane

    if args.all:
        return _print_result(probe_intake_all(stale_mult=args.stale_mult), as_json=args.json)
    return _print_result(
        probe_intake_lane(args.lane, stale_mult=args.stale_mult),
        as_json=args.json,
    )


def cmd_r2(args: argparse.Namespace) -> int:
    from app.database.session import SessionLocal
    from app.services.silent_fail_probes import probe_storage_hub_r2_export

    db = SessionLocal()
    try:
        payload = probe_storage_hub_r2_export(
            db, stale_mult=args.stale_mult, sample=args.sample
        )
    finally:
        db.close()
    return _print_result(payload, as_json=args.json)


def cmd_enrich(args: argparse.Namespace) -> int:
    from app.services.silent_fail_probes import probe_enrich_backlog

    return _print_result(
        probe_enrich_backlog(stale_mult=args.stale_mult),
        as_json=args.json,
    )


def cmd_all(args: argparse.Namespace) -> int:
    from app.services.silent_fail_probes import probe_enrich_backlog, probe_intake_all

    results: list[dict[str, Any]] = [probe_intake_all(stale_mult=args.stale_mult)]
    try:
        from app.database.session import SessionLocal
        from app.services.silent_fail_probes import probe_storage_hub_r2_export

        db = SessionLocal()
        try:
            results.append(
                probe_storage_hub_r2_export(
                    db, stale_mult=args.stale_mult, sample=args.sample
                )
            )
        finally:
            db.close()
    except Exception as e:
        results.append(
            {
                "id": "storage_hub_r2_export",
                "verdict": "blocked",
                "error": str(e)[:300],
            }
        )

    try:
        results.append(probe_enrich_backlog(stale_mult=args.stale_mult))
    except Exception as e:
        results.append(
            {
                "id": "enrich_backlog",
                "verdict": "blocked",
                "error": str(e)[:300],
            }
        )

    order = {"never_seen": 0, "stale": 1, "blocked": 2, "ok": 3, "idle": 4}
    worst = min(results, key=lambda r: order.get(str(r.get("verdict")), 9))
    payload = {
        "id": "silent_fail_all",
        "verdict": worst.get("verdict"),
        "probes": results,
    }
    return _print_result(payload, as_json=args.json)


def main() -> int:
    _bootstrap()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(
        prog="silent_fail_probe",
        description="Readonly silent-fail probes (ok|stale|never_seen|idle|blocked)",
    )
    p.add_argument("--json", action="store_true", help="Full JSON payload")
    p.add_argument(
        "--stale-mult",
        type=float,
        default=2.0,
        help="stale if age > interval_minutes * mult (r2 default override via subcmd)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    intake = sub.add_parser("intake", help="Pilot B — intake last_run Redis")
    intake.add_argument("--lane", default="inbox", help="Lane key (default inbox)")
    intake.add_argument("--all", action="store_true", help="All content lanes")
    intake.set_defaults(func=cmd_intake)

    r2 = sub.add_parser("r2-export", help="Pilot D — storage-hub-r2-export exported_at")
    r2.add_argument("--sample", type=int, default=80, help="Media rows to scan for stamps")
    r2.add_argument(
        "--stale-mult",
        type=float,
        default=3.0,
        help="stale if age > interval * mult (default 3 for Beat export)",
    )
    r2.set_defaults(func=cmd_r2)

    enrich = sub.add_parser(
        "enrich-backlog",
        help="Beat enrich-backlog-sweep last_success Redis stamp",
    )
    enrich.set_defaults(func=cmd_enrich)

    all_p = sub.add_parser("all", help="Intake aggregate + r2-export + enrich-backlog")
    all_p.add_argument("--sample", type=int, default=80)
    all_p.set_defaults(func=cmd_all)

    args = p.parse_args()
    # r2-export has its own stale-mult default on the subparser; argparse may leave
    # parent --stale-mult on intake/all. cmd_r2 reads args.stale_mult from subparser.
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
