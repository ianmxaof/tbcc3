#!/usr/bin/env python3
"""
TBCC headless CLI — run ops without the dashboard.

  cd tbcc/backend && py -3.13 scripts/tbcc_cli.py post send 33 --sync
  py -3.13 scripts/tbcc_cli.py campaign deploy --post-id 33 --sync
  py -3.13 scripts/tbcc_cli.py campaign audit
  py -3.13 scripts/tbcc_cli.py scrape mega --direct-only
  py -3.13 scripts/tbcc_cli.py buffer armory --relay --scheduled
  py -3.13 scripts/tbcc_cli.py buffer refill
  py -3.13 scripts/tbcc_cli.py income summary
  py -3.13 scripts/tbcc_cli.py income add --source linkvertise --amount 42.50
  py -3.13 scripts/tbcc_cli.py income sync --sources bmc,linkvertise
  py -3.13 scripts/tbcc_cli.py pack inventory --list
  py -3.13 scripts/tbcc_cli.py watermark analyze "D:/clips"
  py -3.13 scripts/tbcc_cli.py watermark apply "D:/clips"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()


def _json(obj) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def cmd_post_send(args: argparse.Namespace) -> int:
    from app.database.session import SessionLocal
    from app.services.campaign_deploy_service import DeployOptions, deploy_scheduled_post

    db = SessionLocal()
    try:
        result = deploy_scheduled_post(
            db,
            int(args.post_id),
            DeployOptions(telegram=True, sync=bool(args.sync), reshuffle_album=bool(args.reshuffle), trigger="cli"),
        )
        _json(result.to_dict())
        return 0 if result.telegram.status in ("ok", "queued", "delegated") else 1
    finally:
        db.close()


def cmd_campaign_deploy(args: argparse.Namespace) -> int:
    from app.database.session import SessionLocal
    from app.services.campaign_deploy_service import DeployOptions, deploy_scheduled_post

    db = SessionLocal()
    try:
        opt = DeployOptions(
            telegram=not args.no_telegram,
            buffer=args.buffer,
            discord=args.discord,
            sync=bool(args.sync),
            reshuffle_album=bool(args.reshuffle),
            trigger="cli",
        )
        if args.campaign_group_id:
            from app.models.scheduled_text_post import ScheduledTextPost

            leader = (
                db.query(ScheduledTextPost)
                .filter(ScheduledTextPost.campaign_group_id == args.campaign_group_id)
                .order_by(ScheduledTextPost.id)
                .first()
            )
            if not leader:
                print("Campaign not found", file=sys.stderr)
                return 1
            post_id = int(leader.id)
        else:
            post_id = int(args.post_id)
        result = deploy_scheduled_post(db, post_id, opt)
        _json(result.to_dict())
        ok = result.telegram.status in ("ok", "queued", "delegated", "skipped") or not opt.telegram
        return 0 if ok else 1
    finally:
        db.close()


def cmd_income_summary(args: argparse.Namespace) -> int:
    from app.database.session import SessionLocal
    from app.services.income_ledger import income_summary

    db = SessionLocal()
    try:
        days = int(args.days) if args.days else None
        result = income_summary(db, days=days, backfill=not args.no_backfill)
        _json(result)
        return 0
    finally:
        db.close()


def cmd_income_backfill(_args: argparse.Namespace) -> int:
    from app.database.session import SessionLocal
    from app.services.income_ledger import backfill_subscription_income

    db = SessionLocal()
    try:
        _json(backfill_subscription_income(db))
        return 0
    finally:
        db.close()


def cmd_income_add(args: argparse.Namespace) -> int:
    from app.database.session import SessionLocal
    from app.services.income_ledger import record_manual_income

    db = SessionLocal()
    try:
        result = record_manual_income(
            db,
            source=args.source,
            amount_usd=float(args.amount),
            source_label=args.label or None,
            period_key=args.period or None,
            notes=args.notes or None,
            promo_affiliate_link_id=int(args.affiliate_id) if args.affiliate_id else None,
        )
        _json(result)
        return 0 if result.get("ok") else 1
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    finally:
        db.close()


def cmd_income_sync(args: argparse.Namespace) -> int:
    from app.database.session import SessionLocal
    from app.services.income_sync import sync_external_income

    db = SessionLocal()
    try:
        sources = [s.strip() for s in args.sources.split(",") if s.strip()] if args.sources else None
        _json(sync_external_income(db, sources=sources, headed=bool(args.headed)))
        return 0
    finally:
        db.close()


def cmd_campaign_audit(_args: argparse.Namespace) -> int:
    from app.database.session import SessionLocal
    from app.services.campaign_deploy_service import audit_scheduled_posts, list_recent_deploys

    db = SessionLocal()
    try:
        _json({"schedules": audit_scheduled_posts(db), "recent_deploys": list_recent_deploys(db, limit=20)})
        return 0
    finally:
        db.close()


def cmd_scrape_mega(args: argparse.Namespace) -> int:
    from app.database.session import SessionLocal
    from app.workers.mega_scraper_worker import create_link_scrape_run, run_mega_scrape_job

    db = SessionLocal()
    try:
        label = str(args.chat_id) if args.chat_id else "curated channels"
        run = create_link_scrape_run(db, label=label, chat_id=args.chat_id, trigger="cli")
        async_result = run_mega_scrape_job.delay(
            run.id,
            chat_ids=[int(args.chat_id)] if args.chat_id else None,
            kinds=["direct_host", "mixed"] if args.direct_only else None,
            message_limit=int(args.limit),
            include_obfuscated=not args.direct_only,
            execute=not args.dry_run,
        )
        run.celery_task_id = async_result.id
        db.commit()
        _json({"status": "scheduled", "run_id": run.id, "celery_task_id": async_result.id})
        return 0
    finally:
        db.close()


def cmd_buffer_armory(args: argparse.Namespace) -> int:
    from app.database.session import SessionLocal
    from app.services.seed_aof_buffer_armory import seed_relay_buffer_armory, seed_scheduled_buffer_armory

    db = SessionLocal()
    try:
        report = {}
        if args.relay or (not args.relay and not args.scheduled):
            report["relay"] = seed_relay_buffer_armory(db, replace=not args.append)
        if args.scheduled or (not args.relay and not args.scheduled):
            report["scheduled"] = seed_scheduled_buffer_armory(
                db, post_id=args.post_id, replace=not args.append
            )
        _json(report)
        return 0
    finally:
        db.close()


def cmd_buffer_refill(_args: argparse.Namespace) -> int:
    from app.workers.buffer_armory_worker import refill_buffer_armory

    _json(refill_buffer_armory())
    return 0


def cmd_pack_import(args: argparse.Namespace) -> int:
    from scripts.import_mega_folders_to_pack_pool import main as import_main

    argv = []
    if args.file:
        argv.append(str(args.file))
    if args.execute:
        argv.append("--execute")
    if args.wire_scheduler:
        argv.append("--wire-scheduler")
    if args.source_note:
        argv.extend(["--source-note", args.source_note])
    old_argv = sys.argv
    try:
        sys.argv = ["import_mega_folders_to_pack_pool.py", *argv]
        import_main()
    finally:
        sys.argv = old_argv
    return 0


def cmd_pack_clip(args: argparse.Namespace) -> int:
    from scripts.clip_mega_to_pack_pool import main as clip_main

    argv = []
    if args.url:
        argv.extend(["--url", args.url])
    if args.label:
        argv.extend(["--label", args.label])
    if args.execute:
        argv.append("--execute")
    if args.wire_scheduler:
        argv.append("--wire-scheduler")
    if args.no_wire_scheduler:
        argv.append("--no-wire-scheduler")
    if args.append_export:
        argv.append("--append-export")
    if args.source_note:
        argv.extend(["--source-note", args.source_note])
    old_argv = sys.argv
    try:
        sys.argv = ["clip_mega_to_pack_pool.py", *argv]
        clip_main()
    finally:
        sys.argv = old_argv
    return 0


def cmd_watermark(args: argparse.Namespace) -> int:
    import importlib.util

    path = Path(__file__).resolve().parent / "watermark_local.py"
    spec = importlib.util.spec_from_file_location("watermark_local_cli", path)
    if spec is None or spec.loader is None:
        print("watermark_local.py not found", file=sys.stderr)
        return 1
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    argv = [args.watermark_cmd, str(args.path)]
    if args.watermark_cmd == "apply":
        if args.dry_run:
            argv.append("--dry-run")
        if args.output_dir:
            argv.extend(["--output-dir", str(args.output_dir)])
        if args.no_recursive:
            argv.append("--no-recursive")
    return int(mod.main(argv))


def cmd_pack_inventory(args: argparse.Namespace) -> int:
    from scripts.mega_inventory_to_pack_pool import main as inventory_main

    argv = []
    if args.list:
        argv.append("--list")
    if args.root:
        argv.extend(["--root", args.root])
    if args.rename_prefix:
        argv.extend(["--rename-prefix", args.rename_prefix])
    if args.export_links:
        argv.extend(["--export-links", str(args.export_links)])
    if args.execute:
        argv.append("--execute")
    if args.wire_scheduler:
        argv.append("--wire-scheduler")
    if args.skip_empty:
        argv.append("--skip-empty")
    old_argv = sys.argv
    try:
        sys.argv = ["mega_inventory_to_pack_pool.py", *argv]
        inventory_main()
    finally:
        sys.argv = old_argv
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="tbcc_cli", description="TBCC headless operator CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    post = sub.add_parser("post", help="Scheduled post operations")
    post_sub = post.add_subparsers(dest="post_cmd", required=True)
    ps = post_sub.add_parser("send", help="Send a scheduled post")
    ps.add_argument("post_id", type=int)
    ps.add_argument("--sync", action="store_true", help="Run inline (blocks until Telegram finishes)")
    ps.add_argument("--reshuffle", action="store_true")
    ps.set_defaults(func=cmd_post_send)

    camp = sub.add_parser("campaign", help="Multi-surface campaign deploy")
    camp_sub = camp.add_subparsers(dest="camp_cmd", required=True)
    cd = camp_sub.add_parser("deploy", help="Deploy Telegram + optional Buffer/Discord")
    cd.add_argument("--post-id", type=int)
    cd.add_argument("--campaign-group-id", type=str, default=None)
    cd.add_argument("--sync", action="store_true")
    cd.add_argument("--reshuffle", action="store_true")
    cd.add_argument("--no-telegram", action="store_true")
    cd.add_argument("--buffer", action="store_true", default=None)
    cd.add_argument("--no-buffer", action="store_true")
    cd.add_argument("--discord", action="store_true", default=None)
    cd.add_argument("--no-discord", action="store_true")
    cd.set_defaults(func=cmd_campaign_deploy)
    ca = camp_sub.add_parser("audit", help="List schedules + recent deploy ledger")
    ca.set_defaults(func=cmd_campaign_audit)

    scrape = sub.add_parser("scrape", help="Scrape jobs")
    scrape_sub = scrape.add_subparsers(dest="scrape_cmd", required=True)
    sm = scrape_sub.add_parser("mega", help="Mega / paste link scrape")
    sm.add_argument("--chat-id", type=int, default=None)
    sm.add_argument("--limit", type=int, default=40)
    sm.add_argument("--direct-only", action="store_true", default=True)
    sm.add_argument("--dry-run", action="store_true")
    sm.set_defaults(func=cmd_scrape_mega)

    buf = sub.add_parser("buffer", help="Buffer X armory")
    buf_sub = buf.add_subparsers(dest="buf_cmd", required=True)
    ba = buf_sub.add_parser("armory", help="Stock buffer_x_queue captions")
    ba.add_argument("--relay", action="store_true")
    ba.add_argument("--scheduled", action="store_true")
    ba.add_argument("--post-id", type=int, default=None)
    ba.add_argument("--append", action="store_true")
    ba.set_defaults(func=cmd_buffer_armory)
    br = buf_sub.add_parser("refill", help="Top up queues below min depth")
    br.set_defaults(func=cmd_buffer_refill)

    wm = sub.add_parser("watermark", help="Local AOF promo watermark burn-in")
    wm_sub = wm.add_subparsers(dest="watermark_cmd", required=True)
    wma = wm_sub.add_parser("analyze", help="List images/videos in folder")
    wma.add_argument("path", type=Path)
    wma.add_argument("--no-recursive", action="store_true")
    wma.set_defaults(func=cmd_watermark)
    wmp = wm_sub.add_parser("apply", help="Watermark folder contents in place")
    wmp.add_argument("path", type=Path)
    wmp.add_argument("--dry-run", action="store_true")
    wmp.add_argument("--output-dir", type=Path, default=None)
    wmp.add_argument("--no-recursive", action="store_true")
    wmp.set_defaults(func=cmd_watermark)

    pack = sub.add_parser("pack", help="MEGA pack pool import")
    pack_sub = pack.add_subparsers(dest="pack_cmd", required=True)
    pi = pack_sub.add_parser("import", help="Import mega_pack_folders.txt → loot pool")
    pi.add_argument("--file", type=Path, default=None)
    pi.add_argument("--execute", action="store_true")
    pi.add_argument("--wire-scheduler", action="store_true")
    pi.add_argument("--source-note", default="mega_inventory")
    pi.set_defaults(func=cmd_pack_import)
    pc = pack_sub.add_parser("clip", help="Clipboard Mega URL → gate wrap → pool")
    pc.add_argument("--url", default="", help="Mega URL (default: system clipboard)")
    pc.add_argument("--label", default="")
    pc.add_argument("--execute", action="store_true")
    pc.add_argument("--wire-scheduler", action="store_true")
    pc.add_argument("--no-wire-scheduler", action="store_true")
    pc.add_argument("--append-export", action="store_true")
    pc.add_argument("--source-note", default="mega_clipboard")
    pc.set_defaults(func=cmd_pack_clip)
    pinv = pack_sub.add_parser("inventory", help="MEGA account folders → export → pool")
    pinv.add_argument("--list", action="store_true")
    pinv.add_argument("--root", default="")
    pinv.add_argument("--rename-prefix", default="")
    pinv.add_argument("--export-links", type=Path, default=None)
    pinv.add_argument("--execute", action="store_true")
    pinv.add_argument("--wire-scheduler", action="store_true")
    pinv.add_argument("--skip-empty", action="store_true")
    pinv.set_defaults(func=cmd_pack_inventory)

    inc = sub.add_parser("income", help="Unified internal income rollup")
    inc_sub = inc.add_subparsers(dest="inc_cmd", required=True)
    isum = inc_sub.add_parser("summary", help="Totals by source (USD + Stars)")
    isum.add_argument("--days", type=int, default=None, help="Limit to last N days (earned_at)")
    isum.add_argument("--no-backfill", action="store_true", help="Skip subscription backfill")
    isum.set_defaults(func=cmd_income_summary)
    ib = inc_sub.add_parser("backfill", help="Seed ledger from existing subscriptions")
    ib.set_defaults(func=cmd_income_backfill)
    ia = inc_sub.add_parser("add", help="Manual external income entry (USD)")
    ia.add_argument("--source", required=True, help="linkvertise|admaven|workink|bmc|affiliate|…")
    ia.add_argument("--amount", type=float, required=True)
    ia.add_argument("--label", default="")
    ia.add_argument("--period", default="", help="Period key e.g. 2026-W26")
    ia.add_argument("--notes", default="")
    ia.add_argument("--affiliate-id", type=int, default=None)
    ia.set_defaults(func=cmd_income_add)
    isync = inc_sub.add_parser("sync", help="Sync external platforms (delta from cumulative totals)")
    isync.add_argument("--sources", default="", help="Comma-separated: linkvertise,admaven,workink,bmc")
    isync.add_argument("--headed", action="store_true", help="Headed browser for gate dashboard scrape")
    isync.set_defaults(func=cmd_income_sync)

    args = p.parse_args()
    if getattr(args, "camp_cmd", None) == "deploy":
        if args.no_buffer:
            args.buffer = False
        elif args.buffer:
            args.buffer = True
        else:
            args.buffer = None
        if args.no_discord:
            args.discord = False
        elif args.discord:
            args.discord = True
        else:
            args.discord = None
        if not args.post_id and not args.campaign_group_id:
            p.error("deploy requires --post-id or --campaign-group-id")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
