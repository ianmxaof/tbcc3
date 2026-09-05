#!/usr/bin/env python3
"""Readonly silent-fail probes — print ok|stale|never_seen|idle|blocked (exit 0).

Usage (from tbcc/backend):

  py -3.13 scripts/silent_fail_probe.py intake --lane inbox
  py -3.13 scripts/silent_fail_probe.py intake --all
  py -3.13 scripts/silent_fail_probe.py drain
  py -3.13 scripts/silent_fail_probe.py drain --lane taboo
  py -3.13 scripts/silent_fail_probe.py r2-export
  py -3.13 scripts/silent_fail_probe.py enrich-backlog
  py -3.13 scripts/silent_fail_probe.py vault-ingest
  py -3.13 scripts/silent_fail_probe.py money-path
  py -3.13 scripts/silent_fail_probe.py all

No bot Start, no restarts. Requires REDIS_URL for intake; DATABASE_URL for r2-export.
money-path is public HTTP only; writes llm-rag .../3-Resources/Revenue/money-path-health.md
unless --no-write.
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
    try:
        from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

        load_tbcc_dotenv()
    except Exception:
        pass


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


def cmd_drain(args: argparse.Namespace) -> int:
    from app.services.silent_fail_probes import probe_lane_drain

    return _print_result(probe_lane_drain(args.lane), as_json=args.json)


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

    try:
        from app.services.silent_fail_probes import probe_lance_vault_ingest

        results.append(probe_lance_vault_ingest())
    except Exception as e:
        results.append(
            {
                "id": "lance_vault_ingest",
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

    drain = sub.add_parser(
        "drain", help="Lane drain lock vs real work (no celery inspect — see probe docstring)"
    )
    drain.add_argument("--lane", default=None, help="Lane key (default: every content lane)")
    drain.set_defaults(func=cmd_drain)

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

    def cmd_vault_ingest(args: argparse.Namespace) -> int:
        from app.services.silent_fail_probes import probe_lance_vault_ingest

        return _print_result(
            probe_lance_vault_ingest(stale_hours=args.stale_hours),
            as_json=args.json,
        )

    vault = sub.add_parser("vault-ingest", help="Lance vs knowledge/inbox freshness")
    vault.add_argument("--stale-hours", type=float, default=24.0)
    vault.set_defaults(func=cmd_vault_ingest)

    def cmd_money_path(args: argparse.Namespace) -> int:
        from app.services.money_path_health import probe_money_path

        return _print_result(
            probe_money_path(write_vault=not args.no_write),
            as_json=args.json,
        )

    money = sub.add_parser(
        "money-path",
        help="Public CTA/checkout HTTP sweep + vault money-path-health.md",
    )
    money.add_argument(
        "--no-write",
        action="store_true",
        help="Probe only; do not overwrite 3-Resources/Revenue/money-path-health.md",
    )
    money.set_defaults(func=cmd_money_path)

    all_p = sub.add_parser("all", help="Intake aggregate + r2-export + enrich-backlog + vault-ingest")
    all_p.add_argument("--sample", type=int, default=80)
    all_p.set_defaults(func=cmd_all)

    args = p.parse_args()
    # r2-export has its own stale-mult default on the subparser; argparse may leave
    # parent --stale-mult on intake/all. cmd_r2 reads args.stale_mult from subparser.
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
