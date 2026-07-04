"""
Batch inbound scrapes: Telegram SCRP folders → AOF content pools.

Your Telegram folders (BIG TITS SCRP, MILF SCRP, …) are read via Telethon when possible.
Each folder's channels are mapped to the matching AOF pool; seed defaults fill gaps.

Usage (from tbcc/backend):
  py -3.13 scripts/run_aof_batch_scrapes.py --list-folders
  py -3.13 scripts/run_aof_batch_scrapes.py --batch first
  py -3.13 scripts/run_aof_batch_scrapes.py --batch first --execute --limit 80
  py -3.13 scripts/run_aof_batch_scrapes.py --pools bop,goon,abg,voyeur,ai --execute --sync

Requires: API_ID, API_HASH, scraper.session (setup-scraper-session.ps1)
Celery scrape worker for --execute (without --sync).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.aof_scrape_inbound_map import pool_keys_for_batch
from app.database.session import SessionLocal
from app.services.aof_batch_scrape import (
    default_session_stem,
    load_folder_index_from_session,
    plan_batch_scrape,
    queue_batch_scrapes,
    run_batch_scrapes_sync,
)
from app.services.aof_growth_hub import sync_network_schedulers


def _parse_pool_keys(raw: str | None, batch: str | None) -> list[str]:
    if batch:
        return pool_keys_for_batch(batch)
    if raw:
        return [k.strip().lower() for k in raw.split(",") if k.strip()]
    return pool_keys_for_batch("first")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="AOF SCRP folder → pool batch scrapes")
    p.add_argument("--list-folders", action="store_true", help="Print Telegram folders + mapped pool keys")
    p.add_argument("--batch", choices=["first", "second", "third", "remainder", "next"], help="Preset pool batch")
    p.add_argument("--pools", type=str, default="", help="Comma-separated pool keys (overrides --batch)")
    p.add_argument("--limit", type=int, default=80, help="Max messages per source per run (1–500)")
    p.add_argument("--execute", action="store_true", help="Queue Celery scrapes (or --sync for inline)")
    p.add_argument("--sync", action="store_true", help="Run scrapes inline in this process (no Celery)")
    p.add_argument("--no-folder", action="store_true", help="Skip Telegram folder discovery; use seed list only")
    p.add_argument("--no-seeds", action="store_true", help="Skip DEFAULT_INBOUND_SOURCES fallbacks")
    p.add_argument("--sync-pools", action="store_true", help="Ensure GOON/BOP/etc. pools exist before planning")
    args = p.parse_args()

    api_id = os.getenv("API_ID", "").strip()
    api_hash = os.getenv("API_HASH", "").strip()
    if not api_id or not api_hash:
        print("Set API_ID and API_HASH in tbcc/.env")
        sys.exit(1)

    session = default_session_stem()

    if args.list_folders:
        folders = asyncio.run(
            load_folder_index_from_session(api_id, api_hash, session_stem=session)
        )
        from app.data.aof_scrape_inbound_map import match_folder_title_to_pool_key

        print(json.dumps({"session": session, "folders": folders}, indent=2, ensure_ascii=False))
        print("\n--- pool mapping hints ---")
        for title in sorted(folders.keys()):
            key = match_folder_title_to_pool_key(title)
            n = len(folders[title])
            print(f"  {title!r} → {key or '?'} ({n} channel(s))")
        return

    pool_keys = _parse_pool_keys(args.pools, args.batch)
    folder_index: dict = {}
    if not args.no_folder:
        try:
            folder_index = asyncio.run(
                load_folder_index_from_session(api_id, api_hash, session_stem=session)
            )
        except Exception as e:
            print(f"Folder discovery failed ({e}) — using seed sources only.")

    db = SessionLocal()
    try:
        if args.sync_pools:
            sync_network_schedulers(db, execute=True)
            db.commit()

        report = plan_batch_scrape(
            db,
            pool_keys,
            folder_index=folder_index,
            limit=max(1, min(int(args.limit), 500)),
            use_folder=not args.no_folder,
            use_defaults=not args.no_seeds,
        )
        db.commit()

        source_ids: list[int] = []
        for block in report["plan"]:
            for s in block["sources"]:
                source_ids.append(int(s["source_id"]))

        print(json.dumps(report, indent=2, ensure_ascii=False))

        if not args.execute:
            print(f"\n(dry run — {len(source_ids)} source(s) ready; pass --execute to scrape)")
            if report.get("missing_pools"):
                print(f"Missing pools for keys: {report['missing_pools']} — run with --sync-pools")
            return

        if args.sync:
            print("\nRunning inline scrapes (sequential)…")
            results = asyncio.run(
                run_batch_scrapes_sync(
                    api_id,
                    api_hash,
                    source_ids,
                    session_stem=session,
                )
            )
            print(json.dumps({"results": results}, indent=2, ensure_ascii=False)[:8000])
        else:
            report = queue_batch_scrapes(db, source_ids)
            print(json.dumps(report, indent=2, ensure_ascii=False))
            print(
                f"\nQueued {report.get('queued_count', 0)} scrape job(s); "
                f"skipped {report.get('skipped_count', 0)} (forward-disabled / infra)."
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
