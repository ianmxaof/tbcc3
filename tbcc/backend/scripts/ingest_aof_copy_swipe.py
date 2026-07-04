#!/usr/bin/env python3
"""Paste Telegram promo swipes into the AOF copy repo and optionally adapt for a lane."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `python scripts/ingest_aof_copy_swipe.py` from tbcc/backend
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.database.session import SessionLocal
from app.services.aof_copy_swipe import (
    adapt_swipe_sync,
    ingest_swipe_raw,
    list_swipes,
    promote_adapted_to_caption_snippets,
)


def _read_body(args: argparse.Namespace) -> str:
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    if args.text:
        return args.text
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("Provide --text, --file, or pipe stdin")


def main() -> None:
    p = argparse.ArgumentParser(description="Ingest Telegram promo swipes for AOF copy adaptation")
    p.add_argument("--text", help="Raw swipe body")
    p.add_argument("--file", help="File containing raw swipe body")
    p.add_argument("--source", default="manual_paste")
    p.add_argument("--format", default="telegram_promo")
    p.add_argument("--tags", nargs="*", default=[])
    p.add_argument("--tactics", nargs="*", default=[])
    p.add_argument("--notes", default="")
    p.add_argument("--id", dest="swipe_id", default=None)
    p.add_argument("--list", action="store_true", help="List ingested swipes")
    p.add_argument("--adapt", metavar="LANE", help="Adapt swipe after ingest (or use --swipe-id with --adapt-only)")
    p.add_argument("--swipe-id", help="Existing swipe id for --adapt-only")
    p.add_argument("--adapt-only", action="store_true")
    p.add_argument("--promote", action="store_true", help="Save adapted copy to caption_snippets table")
    p.add_argument("--urls", nargs="*", default=[], help="Required URLs for adapted output")
    args = p.parse_args()

    if args.list:
        for s in list_swipes():
            print(f"{s.get('id')}\t{s.get('source')}\t{(s.get('notes') or '')[:60]}")
        return

    swipe_id = args.swipe_id
    if not args.adapt_only:
        body = _read_body(args)
        entry = ingest_swipe_raw(
            body,
            source=args.source,
            format=args.format,
            tags=args.tags,
            tactics=args.tactics,
            notes=args.notes,
            swipe_id=args.swipe_id,
        )
        swipe_id = entry["id"]
        print(json.dumps({"ingested": entry["id"], "tags": entry.get("tags")}, indent=2))

    if args.adapt:
        if not swipe_id:
            raise SystemExit("--swipe-id required for --adapt-only")
        if args.promote:
            db = SessionLocal()
            try:
                result = promote_adapted_to_caption_snippets(
                    db,
                    swipe_id,
                    args.adapt,
                    required_urls=args.urls or None,
                )
                print(json.dumps(result, indent=2))
            finally:
                db.close()
        else:
            text = adapt_swipe_sync(swipe_id, args.adapt, required_urls=args.urls or None)
            print(text)


if __name__ == "__main__":
    main()
