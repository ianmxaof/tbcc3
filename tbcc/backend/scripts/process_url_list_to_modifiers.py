#!/usr/bin/env python3
"""Process a text file / stdin of URLs → validate → LV wrap → loot_modifiers.

Usage:
  python scripts/process_url_list_to_modifiers.py urls.txt --execute
  type rentry.txt | python scripts/process_url_list_to_modifiers.py --execute
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend))

from dotenv import load_dotenv

_env = _backend.parent / ".env"
if _env.exists():
    load_dotenv(_env, override=True)

from app.database.session import SessionLocal
from app.services.mega_link_extract import extract_urls_from_text
from app.services.mega_link_pipeline import build_modifier_payload, resolve_to_file_host
from app.services.mega_scrape_service import _create_modifier, _modifier_exists


def main() -> None:
    p = argparse.ArgumentParser(description="URL list → loot modifiers")
    p.add_argument("file", nargs="?", help="Text file with URLs (or stdin)")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--label-prefix", default="paste")
    args = p.parse_args()

    if args.file:
        text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    else:
        text = sys.stdin.read()

    urls = [e.url for e in extract_urls_from_text(text)]
    if not urls:
        print("No URLs found.", file=sys.stderr)
        raise SystemExit(1)

    db = SessionLocal()
    ok = fail = dup = 0
    try:
        for i, url in enumerate(urls):
            pipeline = resolve_to_file_host(url)
            if not pipeline.ok:
                fail += 1
                print(f"SKIP {url[:80]} — {pipeline.error}")
                continue
            label = f"{args.label_prefix} — {pipeline.destination_url or url}"[:256]
            try:
                payload = build_modifier_payload(pipeline, label=label, source_note="pack_queue")
            except ValueError as e:
                fail += 1
                print(f"SKIP {url[:80]} — {e}")
                continue
            dest = pipeline.destination_url or ""
            if _modifier_exists(db, dest, payload.get("target_url") or ""):
                dup += 1
                print(f"DUP  {dest[:80]}")
                continue
            if args.execute:
                _create_modifier(db, payload, execute=True)
            ok += 1
            print(f"OK   {payload.get('target_url', '')[:100]}")
    finally:
        db.close()

    print(f"\n--- done: ok={ok} dup={dup} fail={fail} execute={args.execute}")


if __name__ == "__main__":
    main()
