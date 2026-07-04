#!/usr/bin/env python3
"""
Import MEGA folder URLs into the shared AOF pack + loot modifier pool.

Input file (one entry per line):
  https://mega.nz/folder/abc#key
  Pack Label | https://mega.nz/folder/abc#key
  Pack Label<TAB>https://mega.nz/folder/abc#key

Usage:
  cd tbcc/backend
  py -3.13 scripts/import_mega_folders_to_pack_pool.py --execute
  py -3.13 scripts/import_mega_folders_to_pack_pool.py ../docs/samples/mega_pack_folders.txt --execute --wire-scheduler
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.services.loot_pack_pool import queue_url_to_pack_pool, refresh_aof_packs_scheduler

_MEGA_URL_RE = re.compile(r"https?://(?:mega\.nz|mega\.co\.nz)/[^\s]+", re.IGNORECASE)


def _parse_line(raw: str) -> tuple[str | None, str] | None:
    line = (raw or "").strip()
    if not line or line.startswith("#"):
        return None
    if "|" in line:
        label, _, url_part = line.partition("|")
        url_m = _MEGA_URL_RE.search(url_part)
        if url_m:
            return label.strip() or None, url_m.group(0).rstrip(".,;)]")
    if "\t" in line:
        label, _, url_part = line.partition("\t")
        url_m = _MEGA_URL_RE.search(url_part)
        if url_m:
            return label.strip() or None, url_m.group(0).rstrip(".,;)]")
    url_m = _MEGA_URL_RE.search(line)
    if url_m:
        return None, url_m.group(0).rstrip(".,;)]")
    return None


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    default_file = _backend.parent / "docs" / "samples" / "mega_pack_folders.txt"
    p = argparse.ArgumentParser(description="MEGA folder URLs → AOF pack / loot modifier pool")
    p.add_argument("file", nargs="?", type=Path, default=default_file, help="Input URL list")
    p.add_argument("--execute", action="store_true", help="Write loot_modifiers rows")
    p.add_argument("--wire-scheduler", action="store_true", help="Refresh AOF PACKS seed rotation after import")
    p.add_argument("--source-note", default="mega_inventory", help="loot_modifiers.source_note prefix")
    args = p.parse_args()

    if not args.file.is_file():
        print(f"File not found: {args.file}", file=sys.stderr)
        raise SystemExit(1)

    rows: list[tuple[str | None, str]] = []
    for raw in args.file.read_text(encoding="utf-8", errors="replace").splitlines():
        parsed = _parse_line(raw)
        if parsed:
            rows.append(parsed)

    if not rows:
        print("No MEGA URLs found in input.", file=sys.stderr)
        raise SystemExit(1)

    db = SessionLocal()
    created = dup = fail = 0
    try:
        for label, url in rows:
            if not args.execute:
                print(f"DRY  {label or '(auto)'}  {url[:90]}")
                continue
            result = queue_url_to_pack_pool(
                db,
                url,
                label=label,
                source_note=args.source_note,
            )
            if not result.get("ok"):
                fail += 1
                print(f"FAIL {url[:80]} — {result.get('error')}")
                continue
            if result.get("duplicate"):
                dup += 1
                print(f"DUP  {result.get('destination_url', url)[:80]}")
                continue
            created += 1
            mod = result.get("modifier") or {}
            print(
                f"OK   id={mod.get('id')} tier={mod.get('min_rarity_tier')} "
                f"{mod.get('label', '')[:40]} → {(mod.get('target_url') or '')[:70]}"
            )

        if args.execute and args.wire_scheduler and created > 0:
            sched = refresh_aof_packs_scheduler(db)
            if sched.get("ok"):
                print(f"SCHEDULER wired modifiers={sched.get('modifier_count')}")
            else:
                print(f"SCHEDULER skip: {sched.get('error')}", file=sys.stderr)
    finally:
        db.close()

    mode = "execute" if args.execute else "dry-run"
    print(f"\n--- {mode}: rows={len(rows)} created={created} dup={dup} fail={fail}")


if __name__ == "__main__":
    main()
