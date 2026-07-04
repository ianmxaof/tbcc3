#!/usr/bin/env python3
"""
MEGA account inventory → rename folders → export links → AOF pack / loot pool.

Backends:
  rclone (default) — TBCC_MEGA_RCLONE_REMOTE=mega  (works with 2FA via configured remote)
  mega.py          — TBCC_MEGA_BACKEND=mega.py + TBCC_MEGA_EMAIL/PASSWORD

Usage:
  cd tbcc/backend
  py -3.13 scripts/mega_inventory_to_pack_pool.py --list
  py -3.13 scripts/mega_inventory_to_pack_pool.py --execute --batch-limit 10 --inject-readme --inject-logos --wire-scheduler
  # Folder rename: @AOFMAINHUB · 13.7GB · 698 Files · ModelName · MEGA PACK · VIP
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.services.aof_network_promo_text import build_mega_pack_readme_text
from app.services.loot_pack_pool import POOL_NAME, queue_url_to_pack_pool, refresh_aof_packs_scheduler
from app.services.mega_pack_naming import (
    apply_pack_brand_rename_rclone,
    extract_pack_theme,
    is_pack_already_branded,
    pack_brand_rename_enabled,
    rebrand_legacy_packs_enabled,
    target_branded_pack_rename,
)
from app.services.mega_pack_previews import import_pack_preview_images
from app.services.mega_account_client import (
    MegaFolderEntry,
    apply_rename_prefix,
    export_folder_link,
    list_mega_folders,
    login_mega_api,
    mega_readme_filename_from_env,
    mega_rename_prefix_from_env,
    upload_text_to_folder,
)
from app.services.aof_pack_logos import (
    aof_logos_mega_folder_from_env,
    local_logo_files,
    logo_keep_filenames,
    pick_logo_for_pack,
)
from app.services.mega_rclone_client import (
    apply_rename_suffix_rclone,
    copy_mega_file_to_folder_rclone,
    export_folder_link_rclone,
    folder_has_root_file_rclone,
    list_mega_folder_files_rclone,
    list_mega_folders_rclone,
    mega_link_delay_seconds,
    mega_link_retries_from_env,
    mega_rename_suffix_from_env,
    purge_legacy_root_files_rclone,
    should_skip_folder,
    upload_local_file_to_folder_rclone,
    upload_text_to_folder_rclone,
    use_mega_rclone,
    verify_rclone_mega_access,
)


def _write_export(path: Path, rows: list[tuple[str, str]], *, append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{label} | {url}" if label else url for label, url in rows]
    if append and path.is_file():
        existing = path.read_text(encoding="utf-8", errors="replace").rstrip("\n")
        body = existing + ("\n" if existing else "") + "\n".join(lines)
        path.write_text(body + ("\n" if lines else ""), encoding="utf-8")
        return
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _load_exported_labels(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    labels: set[str] = set()
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = (raw or "").strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            labels.add(line.partition("|")[0].strip().lower())
    return labels


def _filter_folders(folders: list[MegaFolderEntry], only: str) -> list[MegaFolderEntry]:
    if not only.strip():
        return folders
    name = only.strip()
    matched = [e for e in folders if e.name == name]
    if not matched:
        raise SystemExit(f"No folder named {name!r} at mega: root.")
    return matched


def _load_folders(root: str, *, only: str = "") -> tuple[list[MegaFolderEntry], Any | None]:
    if use_mega_rclone():
        verify_rclone_mega_access()
        folders = list_mega_folders_rclone(root_prefix=root or None)
    else:
        api = login_mega_api()
        folders = list_mega_folders(api, root_prefix=root or None)
        return _filter_folders(folders, only), api
    return _filter_folders(folders, only), None


def _resolve_logo_sources() -> tuple[str, list]:
    """Returns ('local'|'mega', items) where items are Path or filename str."""
    local = local_logo_files()
    if local:
        return "local", local
    mega_folder = aof_logos_mega_folder_from_env()
    mega_files = [
        f
        for f in list_mega_folder_files_rclone(mega_folder)
        if Path(f).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
    ]
    if mega_files:
        return "mega", mega_files
    return "none", []


def _upload_pack_logo(
    entry: MegaFolderEntry,
    *,
    source_kind: str,
    logos: list,
    execute: bool,
) -> str | None:
    picked = pick_logo_for_pack(logos, entry.name)
    if not picked:
        return None
    if not execute:
        name = picked.name if hasattr(picked, "name") else str(picked)
        print(f"WOULD_LOGO {entry.name} ← {name}")
        return name if isinstance(name, str) else picked.name
    if source_kind == "local":
        fname = upload_local_file_to_folder_rclone(entry, picked)
    else:
        fname = copy_mega_file_to_folder_rclone(
            src_folder=aof_logos_mega_folder_from_env(),
            src_filename=str(picked),
            entry=entry,
        )
    print(f"LOGO {entry.name} ← {fname}")
    return fname


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    print("mega_inventory: starting…", flush=True)

    p = argparse.ArgumentParser(description="MEGA cloud inventory → pack pool")
    p.add_argument("--list", action="store_true", help="Print folders (no DB writes)")
    p.add_argument("--root", default="", help="Only folders under this path prefix")
    p.add_argument("--only", default="", help="Process a single top-level folder by exact name")
    p.add_argument("--no-rename", action="store_true", help="Skip rename (useful with --only smoke tests)")
    p.add_argument(
        "--legacy-suffix-rename",
        action="store_true",
        help="Append -TME AOFMAINHUB suffix instead of Theme · SIZE · AOFMAINHUB branding",
    )
    p.add_argument("--rename-suffix", default="", help="Legacy suffix rename (with --legacy-suffix-rename)")
    p.add_argument("--rename-prefix", default="", help="Legacy prefix rename (mega.py only)")
    p.add_argument("--export-links", type=Path, default=None, help="Write label | url lines to this file")
    p.add_argument("--execute", action="store_true", help="Apply changes and queue modifiers")
    p.add_argument("--wire-scheduler", action="store_true", help="Refresh AOF PACKS scheduler after queue")
    p.add_argument("--source-note", default="mega_inventory", help="loot_modifiers.source_note prefix")
    p.add_argument("--inject-readme", action="store_true", help="Upload AOF network link README into each folder")
    p.add_argument("--inject-logos", action="store_true", help="Upload one AOF logo into each pack root (local dir or Mega AOF LOGOS)")
    p.add_argument(
        "--extract-previews",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pull image stills from pack folders into AOF PACKS — Promo pool (default: on with --execute)",
    )
    p.add_argument("--purge-legacy", action="store_true", help="Remove legacy uploader README/promo images at folder root")
    p.add_argument("--readme-name", default="", help="README filename (default: TBCC_MEGA_README_FILENAME)")
    p.add_argument("--skip-empty", action="store_true", help="Skip folders that fail export")
    p.add_argument(
        "--resume-after",
        default="",
        help="Skip folders alphabetically before this name (resume a crashed batch)",
    )
    p.add_argument(
        "--links-only",
        action="store_true",
        help="Only export public links and queue (skip rename/readme/logo/purge)",
    )
    p.add_argument(
        "--skip-export",
        action="store_true",
        help="Skip rclone link + pool queue (faster inject pass; run --links-only later)",
    )
    p.add_argument(
        "--require-readme",
        action="store_true",
        help="Only process folders that already have the pack README at root",
    )
    p.add_argument(
        "--batch-limit",
        type=int,
        default=0,
        help="Process at most N pack folders this run (rename/inject/export/queue)",
    )
    p.add_argument(
        "--no-rebrand-legacy",
        action="store_true",
        help="Skip upgrading legacy -TME AOFMAINHUB folders to @AOFMAINHUB format",
    )
    p.add_argument(
        "--link-limit",
        type=int,
        default=0,
        help="Stop after N successful link exports this run (0 = no limit)",
    )
    p.add_argument(
        "--stop-on-rate-limit",
        action="store_true",
        help="Stop batch on Mega Access violation (recommended for small wrap passes)",
    )
    p.add_argument(
        "--skip-exported",
        action="store_true",
        help="Skip folders already listed in --export-links / mega_pack_folders.txt",
    )
    p.add_argument(
        "--append-links",
        action="store_true",
        help="Append new links to export file instead of overwriting",
    )
    args = p.parse_args()

    if args.no_rebrand_legacy:
        os.environ["TBCC_MEGA_PACK_REBRAND_LEGACY"] = "0"

    folders, api = _load_folders(args.root, only=args.only)
    if not folders:
        print("No MEGA folders found.", file=sys.stderr)
        raise SystemExit(1)

    suffix = (args.rename_suffix or mega_rename_suffix_from_env()).strip()
    prefix = (args.rename_prefix or mega_rename_prefix_from_env()).strip()
    use_brand_rename = pack_brand_rename_enabled() and not args.legacy_suffix_rename

    rename_limit = args.batch_limit if args.batch_limit > 0 else 0

    if not args.no_rename and not args.links_only:
        if use_mega_rclone() and use_brand_rename:
            if args.execute:
                changes = apply_pack_brand_rename_rclone(
                    folders, execute=True, limit=rename_limit
                )
                for row in changes:
                    if row.get("renamed") == "true":
                        gb = row.get("size_gb") or "?"
                        fc = row.get("file_count") or "?"
                        print(f"BRAND_RENAME {row['from']} → {row['to']} ({gb} GB, {fc} files)")
                    elif row.get("error"):
                        print(f"WARN rename {row['from']}: {row['error']}", file=sys.stderr)
                    else:
                        print(f"WOULD_BRAND_RENAME {row['from']} → {row['to']}")
                folders, api = _load_folders(args.root, only=args.only)
            else:
                from app.services.mega_rclone_client import folder_size_stats_rclone

                preview = 0
                for entry in folders:
                    if rename_limit > 0 and preview >= rename_limit:
                        break
                    if should_skip_folder(entry.name) or is_pack_already_branded(entry.name):
                        continue
                    try:
                        stats = folder_size_stats_rclone(entry.name)
                    except Exception as e:
                        print(f"WARN rename preview {entry.name}: {e}", file=sys.stderr)
                        continue
                    new_name = target_branded_pack_rename(
                        entry.name,
                        stats.get("size_gb"),
                        file_count=stats.get("file_count"),
                    )
                    if new_name:
                        gb = stats.get("size_gb") or "?"
                        fc = stats.get("file_count") or "?"
                        print(f"WOULD_BRAND_RENAME {entry.name} → {new_name} ({gb} GB, {fc} files)")
                        preview += 1
        elif suffix and use_mega_rclone():
            if args.execute:
                changes = apply_rename_suffix_rclone(folders, suffix=suffix, execute=True)
                for row in changes:
                    if row.get("renamed") == "true":
                        print(f"RENAME {row['from']} → {row['to']}")
                    elif row.get("error"):
                        print(f"WARN rename {row['from']}: {row['error']}", file=sys.stderr)
                    else:
                        print(f"WOULD_RENAME {row['from']} → {row['to']}")
                folders, api = _load_folders(args.root, only=args.only)
            else:
                for entry in folders:
                    from app.services.mega_rclone_client import target_rename_name

                    new_name = target_rename_name(entry.name, suffix=suffix)
                    if new_name:
                        print(f"WOULD_RENAME {entry.name} → {new_name}")
        elif prefix and api:
            if args.execute:
                changes = apply_rename_prefix(api, folders, prefix=prefix, execute=True)
                for row in changes:
                    print(f"RENAME {row['path']}: {row['from']} → {row['to']}")
                folders, api = _load_folders(args.root, only=args.only)
    elif prefix and api and not use_mega_rclone():
        if args.execute:
            changes = apply_rename_prefix(api, folders, prefix=prefix, execute=True)
            for row in changes:
                print(f"RENAME {row['path']}: {row['from']} → {row['to']}")
            folders, api = _load_folders(args.root, only=args.only)

    readme_text = build_mega_pack_readme_text() if args.inject_readme else ""
    readme_name = (args.readme_name or mega_readme_filename_from_env()).strip()
    logo_kind, logo_items = _resolve_logo_sources() if args.inject_logos else ("none", [])
    if args.inject_logos and not logo_items:
        print("WARN no AOF logos found (local dir or Mega AOF LOGOS folder)", file=sys.stderr)
    keep_files = {readme_name.lower()} | logo_keep_filenames(logo_items)

    export_path = args.export_links or (_backend.parent / "docs" / "samples" / "mega_pack_folders.txt")
    exported_labels = _load_exported_labels(export_path) if args.skip_exported else set()
    link_retries = mega_link_retries_from_env(default=1 if args.links_only else 4)

    resume_after = (args.resume_after or "").strip().lower()
    readme_check_name = readme_name or mega_readme_filename_from_env()
    export_rows: list[tuple[str, str]] = []
    links_exported = 0
    folders_processed = 0
    stop_batch = False
    batch_limit = args.batch_limit if args.batch_limit > 0 else 0
    for entry in folders:
        if stop_batch:
            break
        if should_skip_folder(entry.name):
            print(f"SKIP {entry.name} (reserved folder)")
            continue
        if resume_after and entry.name.lower() < resume_after:
            continue
        if args.skip_exported and entry.name.lower() in exported_labels:
            print(f"SKIP {entry.name} (already exported)")
            continue
        if batch_limit > 0 and folders_processed >= batch_limit:
            print(f"STOP batch-limit={batch_limit} reached")
            break
        if args.require_readme:
            if use_mega_rclone():
                if not folder_has_root_file_rclone(entry.name, readme_check_name):
                    print(f"SKIP {entry.name} (no {readme_check_name})")
                    continue
            else:
                print(f"WARN require-readme needs rclone for {entry.name}", file=sys.stderr)
                continue

        if args.purge_legacy and not args.links_only:
            try:
                removed = purge_legacy_root_files_rclone(
                    entry, keep_filenames=keep_files, execute=args.execute
                )
                for name in removed:
                    mark = "PURGED" if args.execute else "WOULD_PURGE"
                    print(f"{mark} {entry.name}/{name}")
            except Exception as e:
                print(f"WARN purge {entry.name}: {e}", file=sys.stderr)

        if args.inject_readme and args.execute and not args.links_only:
            try:
                if use_mega_rclone():
                    uploaded = upload_text_to_folder_rclone(entry, readme_text, dest_filename=readme_name)
                else:
                    uploaded = upload_text_to_folder(api, entry, readme_text, dest_filename=readme_name or None)
                print(f"README {entry.name} ← {uploaded}")
            except Exception as e:
                print(f"WARN readme {entry.name}: {e}", file=sys.stderr)

        if args.inject_logos and logo_items and not args.links_only:
            try:
                if use_mega_rclone():
                    _upload_pack_logo(entry, source_kind=logo_kind, logos=logo_items, execute=args.execute)
                else:
                    print(f"WARN logos require rclone backend for {entry.name}", file=sys.stderr)
            except Exception as e:
                print(f"WARN logo {entry.name}: {e}", file=sys.stderr)

        should_export = args.links_only or (args.execute and not args.skip_export)
        if should_export:
            if args.link_limit > 0 and links_exported >= args.link_limit:
                print(f"STOP link-limit={args.link_limit} reached")
                break
            try:
                if use_mega_rclone():
                    link = export_folder_link_rclone(entry, retries=link_retries)
                else:
                    link = export_folder_link(api, entry)
                entry.public_link = link
                export_rows.append((entry.name, link))
                links_exported += 1
                print(f"LINK {entry.name} → {link[:80]}")
            except Exception as e:
                err = str(e)
                if args.skip_empty:
                    print(f"SKIP export {entry.name}: {err}", file=sys.stderr)
                    continue
                print(f"WARN export {entry.name}: {err}", file=sys.stderr)
                if args.stop_on_rate_limit and "access violation" in err.lower():
                    print("STOP Mega rate limit — run again later for more links", file=sys.stderr)
                    stop_batch = True
                    continue
            if args.links_only and use_mega_rclone():
                delay = mega_link_delay_seconds()
                if delay > 0:
                    time.sleep(delay)

        folders_processed += 1

    if args.list or not args.execute:
        for entry in folders:
            if should_skip_folder(entry.name):
                continue
            link = entry.public_link or "-"
            print(f"{entry.name}\n  {link[:100]}")

    if export_rows and (args.export_links or args.execute):
        _write_export(export_path, export_rows, append=args.append_links)
        print(f"Wrote {len(export_rows)} links → {export_path}")

    if not args.execute:
        actionable = sum(1 for e in folders if not should_skip_folder(e.name))
        print(f"\n--- dry-run: {actionable} pack folders, {len(export_rows)} links (pass --execute)")
        return

    if args.skip_export:
        print(f"\n--- execute: inject-only (skipped export/queue); folders processed")
        return

    db = SessionLocal()
    created = dup = fail = previews_total = 0
    try:
        from app.models.content_pool import ContentPool
        from app.services.mega_rclone_client import folder_size_gb_rclone

        pool = db.query(ContentPool).filter(ContentPool.name == POOL_NAME).first()
        for label, url in export_rows:
            size_gb = folder_size_gb_rclone(label) if use_mega_rclone() else None
            result = queue_url_to_pack_pool(
                db,
                url,
                label=label,
                source_note=args.source_note,
                size_gb=size_gb,
            )
            if not result.get("ok"):
                fail += 1
                print(f"FAIL {label}: {result.get('error')}")
                continue
            if result.get("duplicate"):
                dup += 1
                continue
            created += 1
            mod = result.get("modifier") or {}
            mod_id = mod.get("id")
            print(f"QUEUED id={mod_id} {label} tier={mod.get('min_rarity_tier')}")

            if (
                args.extract_previews
                and pool
                and mod_id
                and use_mega_rclone()
            ):
                prev = import_pack_preview_images(
                    db,
                    folder_name=label,
                    pool_id=int(pool.id),
                    modifier_id=int(mod_id),
                    theme=extract_pack_theme(label),
                    execute=True,
                )
                n = int(prev.get("imported") or 0)
                previews_total += n
                if n:
                    print(f"PREVIEWS id={mod_id} imported={n} media={prev.get('media_ids')}")
                elif prev.get("reason"):
                    print(f"PREVIEWS id={mod_id} skip={prev.get('reason')}")

        if args.wire_scheduler and (created > 0 or dup > 0):
            sched = refresh_aof_packs_scheduler(db)
            print(f"SCHEDULER: ok={sched.get('ok')} modifiers={sched.get('modifier_count')}")
    finally:
        db.close()

    print(f"\n--- execute: links={len(export_rows)} created={created} dup={dup} fail={fail} previews={previews_total}")


if __name__ == "__main__":
    main()
