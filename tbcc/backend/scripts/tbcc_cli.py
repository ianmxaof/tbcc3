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
  py -3.13 scripts/tbcc_cli.py ask "summarize this in one sentence: ..."
  py -3.13 scripts/tbcc_cli.py ask --list-providers
  echo "some text" | py -3.13 scripts/tbcc_cli.py ask
  py -3.13 scripts/tbcc_cli.py llm refresh
  py -3.13 scripts/tbcc_cli.py llm status
  py -3.13 scripts/tbcc_cli.py llm next
  py -3.13 scripts/tbcc_cli.py llm ask "what's the capital of France?"
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


def cmd_ask(args: argparse.Namespace) -> int:
    """One-shot LLM completion over TBCC's existing 12-provider fallback chain
    (app/services/llm_completions.py + llm_provider_fallback.py) — no new provider
    plumbing, just a general terminal entrypoint for it. Usable as a fallback lane
    when the operator's normal AI usage is capped."""
    import asyncio

    from app.services.llm_completions import (
        TextLlmRuntime,
        complete_chat_text_sync,
        resolve_text_llm_runtime,
    )
    from app.services.llm_provider_fallback import (
        DEFAULT_CHAIN,
        complete_chat_text_with_fallback,
        try_resolve_provider,
    )

    if args.list_providers:
        rows = []
        for pid in (*DEFAULT_CHAIN, "openai"):
            rt = try_resolve_provider(pid)
            rows.append({"provider": pid, "configured": rt is not None, "model": rt.model if rt else None})
        _json(rows)
        return 0

    if args.prompt:
        prompt = args.prompt
    elif not sys.stdin.isatty():
        prompt = sys.stdin.read()
    else:
        prompt = ""
    prompt = (prompt or "").strip()
    if not prompt:
        print("No prompt given — pass text as an argument or pipe via stdin", file=sys.stderr)
        return 1

    messages: list[dict[str, str]] = []
    if args.system:
        messages.append({"role": "system", "content": args.system})
    messages.append({"role": "user", "content": prompt})

    primary: TextLlmRuntime | None = None
    if args.provider:
        try:
            primary = resolve_text_llm_runtime(provider=args.provider, model=args.model or None)
        except RuntimeError as e:
            print(f"Could not resolve provider {args.provider!r}: {e}", file=sys.stderr)
            return 1

    try:
        if args.no_fallback:
            text = complete_chat_text_sync(
                messages,
                model=args.model or None,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
                timeout=args.timeout,
                runtime=primary,
            )
        else:
            text = asyncio.run(
                complete_chat_text_with_fallback(
                    messages,
                    primary=primary,
                    model=args.model or None,
                    max_tokens=args.max_tokens,
                    temperature=args.temperature,
                    timeout=args.timeout,
                )
            )
    except Exception as e:
        print(f"LLM call failed: {e}", file=sys.stderr)
        return 1

    if args.json:
        _json({"ok": True, "provider": args.provider or "auto", "reply": text})
    else:
        print(text)
    return 0


def cmd_llm_refresh(args: argparse.Namespace) -> int:
    """Refresh the local model/provider index (tbcc/.tbcc-run/llm_model_index.sqlite3)
    by hitting each configured provider's /models endpoint, plus OpenRouter's real
    usage endpoint. PC-local only — does not touch /zeus/v1/ask or the island."""
    from app.services.llm_model_index import refresh_all_providers

    rows = refresh_all_providers(timeout=args.timeout)
    if args.json:
        _json(rows)
        return 0
    for row in rows:
        if not row.get("configured"):
            print(f"{row['provider']:<12} not configured")
        elif row.get("ok"):
            print(f"{row['provider']:<12} ok  {row.get('model_count', 0)} models")
        else:
            print(f"{row['provider']:<12} FAIL  {row.get('error', '')}")
    return 0


def cmd_llm_status(args: argparse.Namespace) -> int:
    """Show what the local index currently knows: configured/exhausted/model counts."""
    from app.services.llm_model_index import all_provider_status, get_sticky

    rows = all_provider_status()
    if args.json:
        _json({"providers": rows, "cursor": get_sticky()})
        return 0
    sticky = get_sticky()
    if sticky and sticky.get("provider"):
        print(f"sticky: {sticky['provider']} (set {sticky.get('updated_at', '?')})")
    else:
        print("sticky: (none — run `llm next` or `llm ask` to set one)")
    for row in rows:
        configured = row.get("configured")
        state = "unconfigured" if configured == 0 else ("exhausted" if row.get("exhausted") else "ok")
        usage = row.get("usage_remaining")
        usage_s = f" usage_remaining={usage}" if usage is not None else ""
        print(f"{row['provider']:<12} {state:<13} models={row.get('model_count', 0)}{usage_s}")
    return 0


def cmd_llm_next(args: argparse.Namespace) -> int:
    """Advance the sticky cursor to whichever unexhausted provider ranks next
    (known usage-remaining first, then DEFAULT_CHAIN order for the rest)."""
    from app.services.llm_model_index import advance_to_next

    nxt = advance_to_next()
    if nxt is None:
        print("No unexhausted configured provider available — run `llm refresh` first?", file=sys.stderr)
        return 1
    if args.json:
        _json(nxt)
    else:
        print(nxt["provider"])
    return 0


def cmd_llm_ask(args: argparse.Namespace) -> int:
    """Like `ask`, but sticky: uses the last provider `llm next`/`llm ask` picked
    (or the chain default on first run), and on a quota-classified failure,
    auto-cycles to the next unexhausted provider and retries once. CLI-local
    devops convenience only — /zeus/v1/ask and the MCP ask_llm tool stay
    stateless and never read this cursor."""
    import asyncio

    from app.services.llm_completions import TextLlmRuntime, resolve_text_llm_runtime
    from app.services.llm_model_index import (
        advance_to_next,
        get_sticky,
        rank_providers_for_cycle,
        record_failure,
        set_sticky,
    )
    from app.services.llm_provider_fallback import complete_chat_text_with_fallback

    if args.prompt:
        prompt = args.prompt
    elif not sys.stdin.isatty():
        prompt = sys.stdin.read()
    else:
        prompt = ""
    prompt = (prompt or "").strip()
    if not prompt:
        print("No prompt given — pass text as an argument or pipe via stdin", file=sys.stderr)
        return 1

    messages: list[dict[str, str]] = []
    if args.system:
        messages.append({"role": "system", "content": args.system})
    messages.append({"role": "user", "content": prompt})

    provider = args.provider or (get_sticky() or {}).get("provider")
    if not provider:
        ranked = rank_providers_for_cycle()
        provider = ranked[0]["provider"] if ranked else None

    def _resolve(pid: str | None) -> TextLlmRuntime | None:
        if not pid:
            return None
        try:
            return resolve_text_llm_runtime(provider=pid)
        except RuntimeError:
            return None

    primary = _resolve(provider)
    if provider and primary is None:
        print(f"sticky provider {provider!r} no longer configured — falling back to chain", file=sys.stderr)

    for attempt in range(2):
        try:
            text = asyncio.run(
                complete_chat_text_with_fallback(
                    messages,
                    primary=primary,
                    model=args.model or None,
                    max_tokens=args.max_tokens,
                    temperature=args.temperature,
                    timeout=args.timeout,
                )
            )
        except Exception as e:
            used = primary.provider if primary else "auto"
            kind = record_failure(used, primary.model if primary else None, e)
            if kind == "quota" and attempt == 0:
                print(f"{used}: quota exhausted, cycling to next provider…", file=sys.stderr)
                nxt = advance_to_next()
                if nxt is None:
                    print("No unexhausted configured provider left.", file=sys.stderr)
                    return 1
                primary = _resolve(nxt["provider"])
                continue
            print(f"LLM call failed ({kind}): {e}", file=sys.stderr)
            return 1
        else:
            if primary is not None:
                set_sticky(primary.provider, primary.model)
            if args.json:
                _json({"ok": True, "provider": primary.provider if primary else "auto", "reply": text})
            else:
                print(text)
            return 0
    return 1


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

    ask = sub.add_parser("ask", help="One-shot LLM completion via TBCC's provider fallback chain")
    ask.add_argument("prompt", nargs="?", default="", help="Prompt text (omit to read stdin)")
    ask.add_argument("--system", default="", help="Optional system prompt")
    ask.add_argument("-p", "--provider", default="", help="Force a specific provider (else full fallback chain)")
    ask.add_argument("-m", "--model", default="", help="Override model id")
    ask.add_argument("--max-tokens", type=int, default=600)
    ask.add_argument("--temperature", type=float, default=0.7)
    ask.add_argument("--timeout", type=float, default=90.0)
    ask.add_argument("--no-fallback", action="store_true", help="Use only the resolved provider, no chain walk")
    ask.add_argument("--list-providers", action="store_true", help="List configured providers and exit")
    ask.add_argument("--json", action="store_true", help="JSON output instead of raw text")
    ask.set_defaults(func=cmd_ask)

    llm = sub.add_parser("llm", help="Local LLM provider/model index — devops CLI (see also: ask)")
    llm_sub = llm.add_subparsers(dest="llm_cmd", required=True)

    lr = llm_sub.add_parser("refresh", help="Refresh model lists + OpenRouter usage from every configured provider")
    lr.add_argument("--timeout", type=float, default=20.0)
    lr.add_argument("--json", action="store_true")
    lr.set_defaults(func=cmd_llm_refresh)

    lstatus = llm_sub.add_parser("status", help="Show what the local index knows: configured/exhausted/models")
    lstatus.add_argument("--json", action="store_true")
    lstatus.set_defaults(func=cmd_llm_status)

    ln = llm_sub.add_parser("next", help="Advance the sticky cursor to the next unexhausted provider")
    ln.add_argument("--json", action="store_true")
    ln.set_defaults(func=cmd_llm_next)

    lask = llm_sub.add_parser("ask", help="Like `ask`, but sticky + auto-cycles providers on quota exhaustion")
    lask.add_argument("prompt", nargs="?", default="", help="Prompt text (omit to read stdin)")
    lask.add_argument("--system", default="", help="Optional system prompt")
    lask.add_argument("-p", "--provider", default="", help="Force a specific provider for this call")
    lask.add_argument("-m", "--model", default="", help="Override model id")
    lask.add_argument("--max-tokens", type=int, default=600)
    lask.add_argument("--temperature", type=float, default=0.7)
    lask.add_argument("--timeout", type=float, default=90.0)
    lask.add_argument("--json", action="store_true", help="JSON output instead of raw text")
    lask.set_defaults(func=cmd_llm_ask)

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
