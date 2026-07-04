#!/usr/bin/env python3
"""Phase B: MEGA folder (rclone) → watermarked staging → Erome batch upload → pack pool.

Production usage (named folder only):
  py -3.13 scripts/mega_to_erome_upload.py --mega-folder "Pack Name" --execute --max-files 15 --wire-pool

Batch manifest (one browser session, N albums):
  py -3.13 scripts/mega_to_erome_upload.py --batch packs.json --execute --wire-pool

Manifest JSON:
  [
    {"mega_folder": "Pack A", "title": "Model A", "max_files": 12, "modifier_id": null},
    {"mega_folder": "Pack B", "title": "Model B", "max_files": 15}
  ]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.services.erome_promo_wire import wire_batch_results, wire_erome_album_to_modifier
from app.services.erome_upload_provision import (
    AlbumUploadJob,
    save_upload_manifest,
    upload_albums_batch,
)
from app.services.mega_erome_staging import (
    erome_staging_dir,
    pick_smallest_mega_folder,
    stage_mega_folder_for_erome,
)
from app.services.mega_rclone_client import list_mega_folders_rclone, use_mega_rclone, verify_rclone_mega_access


@dataclass
class BatchItem:
    mega_folder: str
    title: str | None = None
    max_files: int | None = None
    modifier_id: int | None = None
    label: str | None = None
    mega_dest_url: str | None = None
    size_gb: float | None = None


def _load_batch(path: Path) -> list[BatchItem]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("batch manifest must be a JSON array")
    out: list[BatchItem] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        folder = str(row.get("mega_folder") or "").strip()
        if not folder:
            continue
        out.append(
            BatchItem(
                mega_folder=folder,
                title=(str(row["title"]).strip() if row.get("title") else None),
                max_files=int(row["max_files"]) if row.get("max_files") is not None else None,
                modifier_id=int(row["modifier_id"]) if row.get("modifier_id") is not None else None,
                label=(str(row["label"]).strip() if row.get("label") else None),
                mega_dest_url=(str(row["mega_dest_url"]).strip() if row.get("mega_dest_url") else None),
                size_gb=float(row["size_gb"]) if row.get("size_gb") is not None else None,
            )
        )
    return out


def cmd_list_mega(limit: int) -> int:
    if not use_mega_rclone():
        print("ERROR: TBCC_MEGA_BACKEND must be rclone", file=sys.stderr)
        return 2
    verify_rclone_mega_access()
    folders = list_mega_folders_rclone()
    print(f"MEGA folders ({len(folders)}):")
    for entry in folders[:limit]:
        print(f"  {entry.name}")
    if len(folders) > limit:
        print(f"  … and {len(folders) - limit} more")
    print("\nDebug — smallest by media file count (slow; do not use in prod):")
    for name, count in pick_smallest_mega_folder(limit=10)[:5]:
        print(f"  {count:4d} files  {name}")
    return 0


def _stage_jobs(items: list[BatchItem], *, max_depth: int, default_max_files: int | None) -> list[AlbumUploadJob]:
    jobs: list[AlbumUploadJob] = []
    for item in items:
        cap = item.max_files if item.max_files is not None else default_max_files
        print(f"Staging MEGA: {item.mega_folder}", flush=True)
        root, files = stage_mega_folder_for_erome(
            item.mega_folder,
            max_files=cap,
            max_depth=max_depth,
        )
        title = item.title or item.label or item.mega_folder[:120]
        jobs.append(
            AlbumUploadJob(
                folder=root,
                files=files,
                title=title,
                mega_folder=item.mega_folder,
                modifier_id=item.modifier_id,
                label=item.label or title,
            )
        )
        print(f"  -> {len(files)} file(s) at {root}", flush=True)
    return jobs


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="MEGA rclone → watermarked Erome batch upload")
    p.add_argument("--list-mega", action="store_true", help="List MEGA folders")
    p.add_argument("--mega-folder", type=str, default="", help="MEGA folder name (required for single --execute)")
    p.add_argument("--batch", type=Path, default=None, help="JSON array of {mega_folder, title, max_files, modifier_id}")
    p.add_argument("--smallest", action="store_true", help="DEBUG ONLY — scan folders to pick smallest")
    p.add_argument("--allow-smallest", action="store_true", help="Allow --smallest with --execute (not for prod)")
    p.add_argument("--dry-run", action="store_true", help="Stage + watermark only")
    p.add_argument("--execute", action="store_true", help="Stage + batch upload to Erome")
    p.add_argument("--max-files", type=int, default=None, help="Default cap per album")
    p.add_argument("--max-depth", type=int, default=4)
    p.add_argument("--title", type=str, default=None)
    p.add_argument("--modifier-id", type=int, default=None, help="Update existing loot_modifiers row")
    p.add_argument("--wire-pool", action="store_true", help="Write album URL + promo template to pack pool")
    p.add_argument("--headed", action="store_true")
    p.add_argument("--keep-staging", action="store_true")
    p.add_argument("--manifest", type=Path, default=None)
    p.add_argument("--list-limit", type=int, default=40)
    p.add_argument("--no-watermark", action="store_true")
    args = p.parse_args()

    if args.list_mega:
        return cmd_list_mega(args.list_limit)

    if not args.dry_run and not args.execute:
        p.print_help()
        return 0

    if not use_mega_rclone():
        print("ERROR: TBCC_MEGA_BACKEND must be rclone", file=sys.stderr)
        return 2
    verify_rclone_mega_access()

    items: list[BatchItem] = []
    if args.batch:
        items = _load_batch(args.batch)
        if not items:
            print("ERROR: batch manifest empty", file=sys.stderr)
            return 2
    else:
        folder = (args.mega_folder or "").strip()
        if args.smallest:
            if args.execute and not args.allow_smallest:
                print(
                    "ERROR: --smallest is debug-only. Use --mega-folder or --batch for production.\n"
                    "       Pass --allow-smallest to override.",
                    file=sys.stderr,
                )
                return 2
            print("Scanning MEGA folders (debug)…", flush=True)
            picks = pick_smallest_mega_folder(limit=20)
            if not picks:
                print("ERROR: No MEGA folders found", file=sys.stderr)
                return 1
            folder = picks[0][0]
            print(f"Selected: {folder} ({picks[0][1]} files est.)")
        if not folder:
            print("ERROR: --mega-folder or --batch required", file=sys.stderr)
            return 2
        items = [
            BatchItem(
                mega_folder=folder,
                title=args.title,
                max_files=args.max_files,
                modifier_id=args.modifier_id,
            )
        ]

    print(f"Staging root: {erome_staging_dir()}", flush=True)
    jobs = _stage_jobs(items, max_depth=args.max_depth, default_max_files=args.max_files)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "albums": [
                        {"mega_folder": j.mega_folder, "staging_path": str(j.folder), "file_count": len(j.files)}
                        for j in jobs
                    ],
                },
                indent=2,
            )
        )
        return 0

    print(f"Batch upload: {len(jobs)} album(s) in one browser session", flush=True)
    results = upload_albums_batch(jobs, headed=args.headed)

    manifest_rows: list[dict] = []
    ok_count = 0
    for job, result in zip(jobs, results):
        row = result.to_dict()
        row["mega_folder"] = job.mega_folder
        row["title"] = job.title
        row["modifier_id"] = job.modifier_id
        row["label"] = job.label
        manifest_rows.append(row)
        out_path = args.manifest or (job.folder / "erome_result.json")
        save_upload_manifest(result, out_path)
        if result.ok:
            ok_count += 1
            print(f"OK #{ok_count}: {result.album_url}  ({job.mega_folder})", flush=True)
        else:
            print(f"FAIL: {job.mega_folder} — {result.error}", file=sys.stderr)

    if args.wire_pool:
        with SessionLocal() as db:
            wired = wire_batch_results(db, manifest_rows)
            for w in wired:
                if w.ok:
                    print(f"  wired mod #{w.modifier_id} promo -> {w.promo_note_path}", flush=True)
                else:
                    print(f"  wire FAIL: {w.error}", file=sys.stderr)

    summary_path = erome_staging_dir() / "batch_results.json"
    summary_path.write_text(json.dumps(manifest_rows, indent=2) + "\n", encoding="utf-8")
    print(f"Summary: {summary_path}")

    if args.keep_staging:
        print(f"Staging kept under {erome_staging_dir()}")

    return 0 if ok_count == len(jobs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
