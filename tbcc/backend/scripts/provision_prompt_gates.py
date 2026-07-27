#!/usr/bin/env python3
"""Provision Linkvertise Text assets for prompt_gate rows (Playwright).

Workflow:
  1. --login           Save publisher session (once)
  2. --record-text     Record Text wizard selectors
  3. --import-json     Upsert catalog rows from JSON file
  4. --status          Config + queue counts
  5. --dry-run         List provision queue (resume-safe)
  6. --probe-active    Probe live slugs; requeue TAKEDOWN rows
  7. --execute         Batch provision pending/failed rows

Install: py -m pip install playwright && py -m playwright install chromium
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

import os as _os

_db_override = (_os.getenv("TBCC_DATABASE_URL_OVERRIDE") or "").strip()
if _db_override:
    _os.environ["DATABASE_URL"] = _db_override

from app.database.session import SessionLocal
from app.services.linkvertise_dashboard_provision import (
    _spec,
    auth_state_path,
    create_dashboard_text_batch,
    flow_config_path,
    load_flow_config,
    login_and_save_session,
    probe_lv_gate,
    record_text_dashboard_flow,
    selectors_ready,
    text_selectors_ready,
)
from app.services.playwright_browser import browser_label, describe_launch_mode, resolve_launch_mode
from app.services.prompt_gate_registry import (
    apply_provision_success,
    import_catalog_items,
    list_provision_queue,
    mark_provision_failed,
    probe_and_requeue_takedowns,
    status_counts,
)


def cmd_status() -> int:
    cfg = load_flow_config()
    auth = auth_state_path()
    print(f"Flow config:       {flow_config_path()}")
    print(f"Browser:           {browser_label()}")
    print(f"Auth state:        {auth} ({'ok' if auth.is_file() else 'MISSING'})")
    print(f"Launch mode:       {describe_launch_mode(storage_state=auth)}")
    print(f"Link selectors:    {selectors_ready(cfg)}")
    print(f"Text selectors:    {text_selectors_ready(cfg)}")
    if not text_selectors_ready(cfg):
        missing = [
            k
            for k in (
                "wizard_start",
                "asset_type_text_option",
                "text_body_input",
                "submit_button",
                "wizard_next_after_url",
                "wizard_next_after_settings",
            )
            if not _spec(cfg, k)
        ]
        print(f"  Text missing:    {', '.join(missing)}")
        print("  Record: py scripts/provision_prompt_gates.py --record-text")
    with SessionLocal() as db:
        try:
            counts = status_counts(db)
            if counts:
                print("Registry counts:   " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
            queue = list_provision_queue(db, limit=20)
            print(f"Provision queue:   {len(list_provision_queue(db))} row(s)")
            for item in queue:
                print(f"  #{item.row.id} key={item.row.key} reason={item.reason} tier={item.row.tier or '-'}")
        except Exception as e:
            print(f"Registry:          (DB unavailable: {e})")
    return 0


def cmd_dry_run(limit: int | None, keys: list[str] | None, include_failed: bool) -> int:
    with SessionLocal() as db:
        queue = list_provision_queue(db, limit=limit, keys=keys, include_failed=include_failed)
        print(f"Would provision {len(queue)} prompt_gate row(s)")
        for item in queue:
            row = item.row
            print(
                f"  #{row.id} key={row.key} reason={item.reason} "
                f"hash={row.body_hash or '?'} tier={row.tier or '-'}"
            )
    return 0


def cmd_import_json(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        print("ERROR: JSON must be a list or {\"items\": [...]}", file=sys.stderr)
        return 2
    with SessionLocal() as db:
        counts = import_catalog_items(db, items)
    print(f"Imported {len(items)} item(s): {counts}")
    return 0


def cmd_probe_active(limit: int | None) -> int:
    with SessionLocal() as db:
        queued = probe_and_requeue_takedowns(db, limit=limit)
    print(f"Requeued {len(queued)} row(s) after TAKEDOWN probe")
    for item in queued:
        print(f"  #{item.row.id} key={item.row.key}")
    return 0


def cmd_execute(
    limit: int | None,
    headed: bool,
    skip_probe: bool,
    keys: list[str] | None,
    no_close: bool,
    include_failed: bool,
) -> int:
    if not text_selectors_ready(load_flow_config()):
        print("ERROR: Text flow not configured. Run --record-text first.", file=sys.stderr)
        return 2
    auth = auth_state_path()
    if resolve_launch_mode(storage_state=auth) == "session" and not auth.is_file() and not headed:
        print("ERROR: Auth missing. Run --login --headed", file=sys.stderr)
        return 2

    ok_count = 0
    with SessionLocal() as db:
        queue = list_provision_queue(db, limit=limit, keys=keys, include_failed=include_failed)
        if not queue:
            print("Nothing in provision queue.")
            return 0

        batch_items = [(item.body, item.title, item.row.key) for item in queue]
        print(f"Batch provision {len(batch_items)} Text asset(s) (resume-safe)")
        for item in queue:
            print(f"  queue #{item.row.id} {item.row.key} ({item.reason})")

        results = create_dashboard_text_batch(batch_items, headed=headed, no_close=no_close)

        for item, (_body, _title, key, lv_or_err) in zip(queue, results):
            row = item.row
            if key != row.key:
                print(f"  WARN key mismatch {key} != {row.key}")
            if not lv_or_err or str(lv_or_err).startswith("ERROR:"):
                mark_provision_failed(db, row, reason=str(lv_or_err or "unknown")[:120])
                print(f"  FAIL #{row.id} {row.key}: {lv_or_err}")
                continue
            if str(lv_or_err).startswith("GUIDELINES:"):
                mark_provision_failed(db, row, reason="guidelines")
                print(f"  FAIL #{row.id} {row.key}: {lv_or_err}")
                continue

            lv_url = str(lv_or_err)
            probe = None
            if not skip_probe:
                probe = probe_lv_gate(lv_url)
                print(f"  #{row.id} {row.key} {lv_url} probe={probe.get('flags')}")
                if "TAKEDOWN" in (probe.get("flags") or []):
                    mark_provision_failed(db, row, reason="takedown_on_probe")
                    print(f"  FAIL #{row.id} {row.key}: probe TAKEDOWN")
                    continue
            else:
                print(f"  #{row.id} {row.key} {lv_url}")

            apply_provision_success(db, row, lv_url, probe=probe)
            ok_count += 1

    print(f"Done: {ok_count}/{len(queue)} provisioned")
    return 0 if ok_count else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Linkvertise Text provisioner for prompt_gate rows")
    p.add_argument("--login", action="store_true", help="Open browser to log in; save session state")
    p.add_argument("--record-text", action="store_true", help="Record Text wizard with Inspector")
    p.add_argument("--status", action="store_true", help="Show config + registry counts")
    p.add_argument("--dry-run", action="store_true", help="List provision queue")
    p.add_argument("--import-json", type=Path, metavar="PATH", help="Upsert catalog from JSON file")
    p.add_argument("--probe-active", action="store_true", help="Probe provisioned slugs; requeue TAKEDOWN")
    p.add_argument("--execute", action="store_true", help="Provision queue rows via Playwright")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--headed", action="store_true")
    p.add_argument("--no-close", action="store_true", help="Leave browser open after --execute")
    p.add_argument("--skip-probe", action="store_true")
    p.add_argument("--no-retry-failed", action="store_true", help="Skip failed rows on --execute")
    p.add_argument("--key", action="append", default=None, help="Only these prompt_gate keys (repeatable)")
    args = p.parse_args()

    if args.login:
        login_and_save_session(headed=True)
        print("\nNext: py scripts/provision_prompt_gates.py --record-text")
        return 0
    if args.record_text:
        record_text_dashboard_flow(headed=True)
        return 0
    if args.import_json:
        return cmd_import_json(args.import_json)
    if args.probe_active:
        return cmd_probe_active(args.limit)
    if args.status:
        return cmd_status()
    if args.dry_run:
        return cmd_dry_run(args.limit, args.key, include_failed=not args.no_retry_failed)
    if args.execute:
        return cmd_execute(
            args.limit,
            args.headed,
            args.skip_probe,
            args.key,
            args.no_close,
            include_failed=not args.no_retry_failed,
        )

    p.print_help()
    return cmd_status()


if __name__ == "__main__":
    raise SystemExit(main())
