#!/usr/bin/env python3
"""Upload a local staging folder to Erome via Playwright (Phase A).

Workflow:
  1. --login      Save Erome session (once)
  2. --record     Record upload click path → refine erome_upload_flow.local.json
  3. --dry-run    List media files in folder
  4. --execute    Upload files → print album URL

Install: py -m pip install playwright && py -m playwright install chromium
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.services.archive_governance import submit_archive_url
from app.services.erome_upload_provision import (
    _spec,
    auth_state_path,
    flow_config_path,
    load_flow_config,
    login_and_save_session,
    record_upload_flow,
    save_upload_manifest,
    scan_staging_folder,
    selectors_ready,
)
from app.services.erome_upload_analytics import EromeUploadParams, merge_sidecar_params
from app.services.erome_upload_policy import check_upload_policy, policy_block_message
from app.services.erome_telegram_ingest import upload_staged_folder
from app.services.playwright_browser import (
    browser_label,
    default_brave_profile_name,
    describe_launch_mode,
    list_brave_profiles,
    resolve_launch_mode,
    use_brave_persistent_profile,
)


def cmd_status() -> int:
    cfg = load_flow_config()
    auth = auth_state_path()
    print(f"Flow config:     {flow_config_path()}")
    print(f"Browser:         {browser_label()}")
    print(f"Automation prof: {default_brave_profile_name()} (freeusegod excluded — set TBCC_BRAVE_PROFILE_NAME)")
    profiles = list_brave_profiles()
    if profiles:
        print("Brave profiles:  " + ", ".join(f"{n}/{f}" for n, f in profiles))
    auth_ok = auth.is_file() or use_brave_persistent_profile()
    print(f"Auth state:      {auth} ({'ok' if auth.is_file() else 'profile session' if use_brave_persistent_profile() else 'MISSING'})")
    print(f"Launch mode:     {describe_launch_mode(storage_state=auth)}")
    print(f"Selectors ready: {selectors_ready(cfg)}")
    print(f"Allowed types:   {', '.join(cfg.allowed_extensions)}")
    if not selectors_ready(cfg):
        missing = [k for k in ("file_input", "submit_button") if not _spec(cfg, k)]
        print(f"  Missing locators: {', '.join(missing)}")
        print("  Record flow: py scripts/erome_codegen.py")
    return 0


def cmd_dry_run(folder: Path, max_files: int | None) -> int:
    cfg = load_flow_config()
    scan = scan_staging_folder(folder, allowed_extensions=cfg.allowed_extensions, max_files=max_files)
    print(f"Folder:   {scan.folder}")
    print(f"Files:    {len(scan.files)}")
    for p in scan.files[:30]:
        print(f"  {p.name}  ({p.stat().st_size // 1024} KB)")
    if len(scan.files) > 30:
        print(f"  … and {len(scan.files) - 30} more")
    if scan.skipped:
        print(f"Skipped:  {len(scan.skipped)} non-media or over limit")
    return 0 if scan.ok else 1


def cmd_execute(
    folder: Path,
    *,
    title: str | None,
    description: str | None,
    tags: list[str] | None,
    headed: bool,
    keep_open: bool,
    max_files: int | None,
    save_archive: bool,
    wire_pool: bool,
    modifier_id: int | None,
    skip_watermark: bool,
    manifest: Path | None,
    force_policy: bool,
    source: str,
    visibility: str | None,
) -> int:
    if not selectors_ready(load_flow_config()):
        print("ERROR: Flow not configured. Set file_input + submit_button locators.", file=sys.stderr)
        return 2
    auth = auth_state_path()
    launch_mode = resolve_launch_mode(storage_state=auth)
    if launch_mode == "session" and not auth.is_file() and not use_brave_persistent_profile() and not headed:
        print("ERROR: Auth state missing. Run --login --headed or set TBCC_BRAVE_PROFILE_NAME.", file=sys.stderr)
        return 2

    cfg = load_flow_config()
    scan = scan_staging_folder(folder, allowed_extensions=cfg.allowed_extensions, max_files=max_files)
    if not scan.ok:
        print(f"ERROR: No media files in {folder}", file=sys.stderr)
        return 1

    params = merge_sidecar_params(
        folder,
        EromeUploadParams(
            title=title or folder.name,
            description=description,
            tags=list(tags or []),
            source=source,
            staging_path=str(folder),
            file_count=len(scan.files),
            force_policy=force_policy,
            visibility=visibility,
        ),
    )
    verdict = check_upload_policy(
        title=params.title,
        file_count=len(scan.files),
        tags=params.tags,
        source=source,
        force=force_policy,
    )
    if verdict.warnings:
        print("Policy warnings:", "; ".join(verdict.warnings), flush=True)
    if not verdict.allowed:
        print(f"BLOCKED: {policy_block_message(verdict)}", file=sys.stderr)
        return 3

    vis = params.visibility or "private"
    print(f"Uploading {len(scan.files)} file(s) from {folder}", flush=True)
    print(f"Title: {params.title}", flush=True)
    print(f"Visibility: {vis} (governance staging)" if vis == "private" else f"Visibility: {vis}", flush=True)
    if params.tags:
        print(f"Tags: {', '.join(params.tags)}", flush=True)

    with SessionLocal() as db:
        result = upload_staged_folder(
            folder,
            title=params.title,
            description=params.description,
            tags=params.tags,
            max_files=max_files,
            skip_watermark=skip_watermark,
            source=source,
            force_policy=force_policy,
            headed=headed,
            keep_open=keep_open,
            visibility=params.visibility,
            db=db,
        )

    if manifest:
        out = save_upload_manifest(result, manifest)
        print(f"Manifest: {out}")

    if not result.ok:
        print(f"FAIL: {result.error}", file=sys.stderr)
        return 1

    print(f"OK: {result.album_url}")
    print(f"Title: {result.title}  files={result.file_count}  visibility={result.visibility}")
    if result.visibility == "private":
        print("Governance: album is PRIVATE — fix title/tags on Erome, then --mark-approved")

    # Archive / pool wire only for public albums (private is not promo-ready)
    if result.visibility == "public" and save_archive and result.album_url:
        with SessionLocal() as db:
            saved = submit_archive_url(
                db,
                value=result.album_url,
                source="erome_upload",
                ref=str(folder),
                note=result.title,
                tags=",".join(params.tags or ["erome", "upload"]),
                origin="import",
                auto_approve=True,
            )
            if saved.get("ok"):
                entry = saved.get("entry") or {}
                print(f"Archive entry #{entry.get('id')} status={saved.get('status')}")
            else:
                print(f"Archive save failed: {saved.get('error')}", file=sys.stderr)

    if result.visibility == "public" and wire_pool and result.album_url:
        from app.services.erome_promo_wire import wire_erome_album_to_modifier

        with SessionLocal() as db:
            wired = wire_erome_album_to_modifier(
                db,
                album_url=result.album_url,
                label=title or folder.name,
                modifier_id=modifier_id,
            )
            if wired.ok:
                print(f"Pack pool mod #{wired.modifier_id} — promo at {wired.promo_note_path}")
            else:
                print(f"Wire pool failed: {wired.error}", file=sys.stderr)

    return 0


def cmd_list_pending() -> int:
    from app.services.erome_upload_governance import governance_summary

    summary = governance_summary()
    print(f"Default visibility: {summary['default_visibility']}")
    print(f"Pending review:     {summary['pending_review']}")
    print(f"Ledger ok total:    {summary['ledger_ok_total']} (private={summary['private_count']} public={summary['public_count']})")
    for row in summary.get("pending") or []:
        print(f"  {row.get('album_url')}  |  {row.get('title')}  |  tags={','.join(row.get('tags') or [])}")
    return 0


def cmd_mark_approved(album_url: str, *, notes: str | None = None) -> int:
    from app.services.erome_upload_governance import STATUS_APPROVED, mark_governance

    out = mark_governance(album_url=album_url, status=STATUS_APPROVED, notes=notes)
    if not out.get("ok"):
        print(f"FAIL: {out.get('error')}", file=sys.stderr)
        return 1
    print(f"Marked approved_public: {album_url}")
    print("Note: flip the album to Public on Erome manually if still private in the UI.")
    return 0


def cmd_seed_intel_week(*, week: str | None, title: str | None) -> int:
    from app.services.erome_upload_governance import intel_week_staging_dir, seed_intel_week_sidecar

    folder = intel_week_staging_dir(week=week)
    out = seed_intel_week_sidecar(folder, title=title)
    print(f"Intel-week folder: {out['folder']}")
    print(f"Sidecar:           {out['sidecar']}")
    print(f"Suggested tags:    {', '.join(out.get('tags') or []) or '(none yet — push browse intel)'}")
    print("Drop pre-approved media into that folder, then:")
    print(f"  py scripts/erome_upload_local.py --execute --path \"{out['folder']}\" --headed")
    return 0


def cmd_promote_public(album_url: str, *, headed: bool) -> int:
    from app.services.erome_upload_provision import promote_album_to_public

    out = promote_album_to_public(album_url, headed=headed)
    if not out.get("ok"):
        print(f"FAIL: {out.get('error')}", file=sys.stderr)
        if out.get("hint"):
            print(out["hint"], file=sys.stderr)
        return 1
    print(f"Promoted public: {out.get('album_url')}")
    return 0


def cmd_promote_pending(*, headed: bool, dry_run: bool, limit: int | None) -> int:
    from app.services.erome_upload_governance import release_pending_albums_on_main_post

    out = release_pending_albums_on_main_post(headed=headed, limit=limit, dry_run=dry_run)
    print(out)
    return 0 if out.get("ok") else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Upload local folder to Erome (Playwright Phase A)")
    p.add_argument("--login", action="store_true", help="Open Erome login and save session cookies")
    p.add_argument(
        "--record",
        action="store_true",
        help="Open Playwright Codegen (Record/Stop) for Erome upload+private flow",
    )
    p.add_argument(
        "--record-inspector",
        action="store_true",
        help="Legacy Inspector pause (Resume only — no Record button)",
    )
    p.add_argument("--status", action="store_true", help="Show config/auth/selector status")
    p.add_argument("--dry-run", action="store_true", help="List media files without uploading")
    p.add_argument("--execute", action="store_true", help="Upload folder to Erome")
    p.add_argument("--path", type=Path, help="Local staging folder with images/videos")
    p.add_argument("--title", type=str, default=None, help="Album title (default from flow config)")
    p.add_argument("--description", type=str, default=None, help="Optional album description")
    p.add_argument("--tags", type=str, default=None, help="Comma-separated Erome tags")
    p.add_argument("--max-files", type=int, default=None, help="Cap number of files uploaded")
    p.add_argument("--headed", action="store_true", help="Show browser window")
    p.add_argument("--keep-open", action="store_true", help="Leave browser open after upload")
    p.add_argument("--save-archive", action="store_true", help="Save album URL to capture archive (approved)")
    p.add_argument("--wire-pool", action="store_true", help="Attach album URL to pack pool modifier + promo template")
    p.add_argument("--modifier-id", type=int, default=None, help="Existing loot_modifiers id (with --wire-pool)")
    p.add_argument("--no-watermark", action="store_true", help="Skip AOF watermark burn-in (not recommended)")
    p.add_argument("--force", action="store_true", help="Bypass rate-limit / duplicate-title policy blocks")
    p.add_argument("--source", type=str, default="cli", help="Analytics source label (cli, context_menu, …)")
    p.add_argument("--manifest", type=Path, default=None, help="Write JSON result manifest to path")
    p.add_argument(
        "--private",
        action="store_true",
        help="Force private/hidden upload (governance staging; default via TBCC_EROME_DEFAULT_VISIBILITY)",
    )
    p.add_argument(
        "--public",
        action="store_true",
        help="Force public publish (skips private governance default)",
    )
    p.add_argument("--list-pending", action="store_true", help="List private uploads awaiting governance review")
    p.add_argument("--mark-approved", type=str, default=None, metavar="ALBUM_URL", help="Mark ledger row approved after manual pass")
    p.add_argument("--promote-public", type=str, default=None, metavar="ALBUM_URL", help="Playwright: flip private album to public")
    p.add_argument("--promote-pending", action="store_true", help="Promote pending private albums (dry-run unless TBCC_EROME_PROMOTE_ON_MAIN_POST=1 or --force-promote)")
    p.add_argument("--force-promote", action="store_true", help="With --promote-pending, run even if env flag is off")
    p.add_argument("--seed-intel-week", action="store_true", help="Create intel-week staging folder + sidecar tags")
    p.add_argument("--week", type=str, default=None, help="ISO week slug for --seed-intel-week (default current)")
    args = p.parse_args()

    if args.status:
        return cmd_status()
    if args.list_pending:
        return cmd_list_pending()
    if args.mark_approved:
        return cmd_mark_approved(args.mark_approved)
    if args.promote_public:
        return cmd_promote_public(args.promote_public, headed=args.headed)
    if args.promote_pending:
        if args.force_promote:
            import os

            os.environ["TBCC_EROME_PROMOTE_ON_MAIN_POST"] = "1"
        return cmd_promote_pending(headed=args.headed, dry_run=args.dry_run, limit=args.max_files)
    if args.seed_intel_week:
        return cmd_seed_intel_week(week=args.week, title=args.title)
    if args.login:
        login_and_save_session(headed=True)
        return 0
    if args.record or args.record_inspector:
        # Prefer real Codegen (Record/Stop). Inspector has Resume only.
        import subprocess

        codegen = Path(__file__).resolve().parent / "erome_codegen.py"
        cmd = [sys.executable, str(codegen)]
        if args.record_inspector:
            cmd.append("--skip-login")
        else:
            cmd.append("--codegen")
        return int(subprocess.call(cmd))
    if args.dry_run:
        if not args.path:
            print("ERROR: --path required for --dry-run", file=sys.stderr)
            return 2
        return cmd_dry_run(args.path, args.max_files)
    if args.execute:
        if not args.path:
            print("ERROR: --path required for --execute", file=sys.stderr)
            return 2
        if args.private and args.public:
            print("ERROR: use only one of --private / --public", file=sys.stderr)
            return 2
        visibility = "private" if args.private else ("public" if args.public else None)
        return cmd_execute(
            args.path,
            title=args.title,
            description=args.description,
            tags=[t.strip() for t in (args.tags or "").split(",") if t.strip()] or None,
            headed=args.headed,
            keep_open=args.keep_open,
            max_files=args.max_files,
            save_archive=args.save_archive,
            wire_pool=args.wire_pool,
            modifier_id=args.modifier_id,
            skip_watermark=args.no_watermark,
            manifest=args.manifest,
            force_policy=args.force,
            source=args.source,
            visibility=visibility,
        )

    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
