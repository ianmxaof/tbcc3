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
  py -3.13 scripts/tbcc_cli.py llm tui
  py -3.13 scripts/tbcc_cli.py llm keys add openrouter
  py -3.13 scripts/tbcc_cli.py llm keys add huggingface --base-url https://api-inference.huggingface.co/v1
  py -3.13 scripts/tbcc_cli.py llm keys list
  py -3.13 scripts/tbcc_cli.py llm models openrouter
  py -3.13 scripts/tbcc_cli.py research scan
  py -3.13 scripts/tbcc_cli.py research scan --seed
  py -3.13 scripts/tbcc_cli.py research scan --dry-run --json
  py -3.13 scripts/tbcc_cli.py slots add --id smoke-echo --category generic-rest --base-url https://httpbin.org --auth-env-key TBCC_SMOKE_KEY --path /post --method POST --json
  py -3.13 scripts/tbcc_cli.py slots list --json
  py -3.13 scripts/tbcc_cli.py slots call smoke-echo --body '{"hello":"pocket"}' --json
  py -3.13 scripts/tbcc_cli.py slots suggest "sk-or-abcdef..." --json
"""
from __future__ import annotations

import argparse
import getpass
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
        if row.get("key_source") == "none":
            state = "unconfigured"
        elif row.get("exhausted"):
            state = "exhausted"
        else:
            state = "ok"
        usage = row.get("usage_remaining")
        usage_s = f" usage_remaining={usage}" if usage is not None else ""
        print(f"{row['provider']:<12} {state:<13} key={row.get('key_source'):<6} models={row.get('model_count', 0)}{usage_s}")
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


def cmd_llm_clear(args: argparse.Namespace) -> int:
    """Manually clear a provider's exhaustion mark (escape hatch for a bad
    classification — see llm_model_index.classify_failure)."""
    from app.services.llm_model_index import clear_exhaustion

    clear_exhaustion(args.provider)
    print(f"{args.provider}: exhaustion cleared")
    return 0


def cmd_llm_models(args: argparse.Namespace) -> int:
    """List the master model catalog (see also: `llm refresh` to populate it)."""
    from app.services.llm_model_index import list_models

    rows = list_models(args.provider)
    if args.json:
        _json(rows)
        return 0
    for row in rows:
        if row["is_free"]:
            price = "free"
        elif row["price_in_per_m"] is not None:
            price = f"${row['price_in_per_m']:.2f}/${row['price_out_per_m']:.2f} per M"
        else:
            price = "?"
        stale = " [stale]" if row["stale"] else ""
        print(f"{row['provider']:<12} {row['model_id']:<48} {row['modality']:<14} {price}{stale}")
    return 0


def cmd_llm_keys_add(args: argparse.Namespace) -> int:
    """Prompt for a key (hidden input — never a --key flag, so it never lands
    in shell history or a process list) and store it locally. Passing
    --base-url registers a brand-new custom/HuggingFace-style provider id;
    without it, this overrides a built-in provider's env var inside the
    rotator only — secretary_bot and /zeus/v1/ask never read this table."""
    from app.services.llm_model_index import is_builtin_provider, set_credential

    provider = args.provider.strip().lower()
    base_url = args.base_url.strip() or None
    if not is_builtin_provider(provider) and not base_url:
        print(
            f"{provider!r} isn't a built-in provider — pass --base-url to register it as a new custom endpoint.",
            file=sys.stderr,
        )
        return 1
    key = getpass.getpass(f"API key for {provider}: ").strip()
    if not key:
        print("No key entered.", file=sys.stderr)
        return 1
    set_credential(provider, key, base_url)
    print(f"{provider}: {'custom provider registered' if base_url else 'stored'}")
    return 0


def cmd_llm_keys_list(args: argparse.Namespace) -> int:
    """Which providers have a key, and from where — never the key value itself."""
    from app.services.llm_model_index import all_provider_ids, key_source, list_credentials

    stored = {c["provider"]: c for c in list_credentials()}
    rows = [
        {"provider": pid, "key_source": key_source(pid), "base_url": stored.get(pid, {}).get("base_url")}
        for pid in all_provider_ids()
    ]
    if args.json:
        _json(rows)
        return 0
    for row in rows:
        base = f" base_url={row['base_url']}" if row["base_url"] else ""
        print(f"{row['provider']:<14} {row['key_source']:<8}{base}")
    return 0


def cmd_llm_keys_remove(args: argparse.Namespace) -> int:
    from app.services.llm_model_index import remove_credential

    if remove_credential(args.provider):
        print(f"{args.provider}: stored key removed")
        return 0
    print(f"{args.provider}: no stored key", file=sys.stderr)
    return 1


def cmd_research_scan(args: argparse.Namespace) -> int:
    """Fetch every configured RSS/Atom source (tbcc/backend/app/data/
    research_scanner_sources.json), dedupe against the local index
    (tbcc/.tbcc-run/research_scanner.sqlite3), and — unless --seed — batch
    new dev-lane items against SPRINT_STATE.md's open work via the stateless
    LLM fallback chain (never the sticky `llm ask` cursor, so an unattended
    cron run can't repoint the operator's interactive rotator). Delivered
    through the tbcc-research-scanner Hermes skill."""
    from app.services.research_scanner import run_scan

    report = run_scan(seed=args.seed, dry_run=args.dry_run, fetch_timeout=args.timeout)
    if args.json:
        _json(report)
        return 0

    tag = " (seeded — no match pass)" if report["seeded"] else " (dry run)" if report["dry_run"] else ""
    print(f"Scanned {len(report['sources'])} sources, {report['new_items_total']} new items{tag}")
    for row in report["sources"]:
        if not row["ok"]:
            print(f"  ! {row['source_id']}: {row.get('error')}")
    for m in report.get("matches") or []:
        print(f"\nMATCH: {m['title']} -> {m['target']}")
        print(f"  why: {m['why']}")
        print(f"  {m['link']}")
    if report.get("other_signal"):
        print(f"\n{len(report['other_signal'])} other-lane items (not matched):")
        for it in report["other_signal"][:10]:
            print(f"  [{it['lane']}] {it['title']} — {it['link']}")
    if report.get("match_error"):
        print(f"\nmatch pass failed: {report['match_error']}", file=sys.stderr)
    return 0


def cmd_llm_tui(args: argparse.Namespace) -> int:
    """Interactive terminal viewer over the local model/provider index. Needs
    `textual` (tbcc/backend/requirements-dev.txt) — not shipped to the island,
    operator-machine install only."""
    try:
        from scripts.llm_tui import main as tui_main
    except ImportError:
        print(
            "textual is not installed. Run:\n"
            "  py -3.13 -m pip install -r requirements-dev.txt",
            file=sys.stderr,
        )
        return 1
    return tui_main()


def cmd_llm_ask(args: argparse.Namespace) -> int:
    """Like `ask`, but sticky and single-provider: uses the last provider
    `llm next`/`llm ask` picked (or the top of the ranking on first run), and
    on a quota-classified failure, auto-cycles to the next unexhausted
    provider and retries once. Deliberately does NOT use the chain-walking
    fallback (`ask`'s default) — that tries every hop internally, so a raised
    exception could come from any of them, making it impossible to say which
    provider actually failed. Exactly one provider is tried per attempt here
    so record_failure() always blames the right one.

    Also picks the specific model (not just the provider) when --model isn't
    given: free-first, then cheapest input/output per million tokens, from
    whatever `llm refresh` cached for that provider — see
    llm_model_index.pick_best_model_for_provider. --prefer-uncensored is
    opt-in per call, off by default; most devops asks just need a model that
    works, not an NSFW-tolerant one.

    CLI-local devops convenience only — /zeus/v1/ask and the MCP ask_llm tool
    stay stateless and never read this cursor."""
    from app.services.llm_completions import TextLlmRuntime, complete_chat_text_sync
    from app.services.llm_model_index import (
        advance_to_next,
        get_sticky,
        pick_best_model_for_provider,
        rank_providers_for_cycle,
        record_failure,
        resolve_runtime_for_rotator,
        set_sticky,
    )

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

    def _resolve(pid: str | None) -> TextLlmRuntime | None:
        if not pid:
            return None
        model = args.model or pick_best_model_for_provider(pid, prefer_uncensored=args.prefer_uncensored)
        return resolve_runtime_for_rotator(pid, model=model)

    provider = args.provider or (get_sticky() or {}).get("provider")
    primary = _resolve(provider)
    if provider and primary is None:
        print(f"{provider!r} no longer configured — picking from the ranking instead", file=sys.stderr)
        provider = None
    if primary is None:
        ranked = rank_providers_for_cycle()
        provider = ranked[0]["provider"] if ranked else None
        primary = _resolve(provider)
    if primary is None:
        print("No configured provider available — run `llm refresh` first?", file=sys.stderr)
        return 1

    for attempt in range(2):
        try:
            text = complete_chat_text_sync(
                messages,
                model=args.model or None,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
                timeout=args.timeout,
                runtime=primary,
            )
        except Exception as e:
            kind = record_failure(primary.provider, primary.model, e)
            if kind == "quota" and attempt == 0:
                print(f"{primary.provider}: quota exhausted, cycling to next provider…", file=sys.stderr)
                nxt = advance_to_next()
                if nxt is None:
                    print("No unexhausted configured provider left.", file=sys.stderr)
                    return 1
                next_primary = _resolve(nxt["provider"])
                if next_primary is None:
                    print("No unexhausted configured provider left.", file=sys.stderr)
                    return 1
                primary = next_primary
                continue
            print(f"LLM call failed ({kind}): {e}", file=sys.stderr)
            return 1
        else:
            set_sticky(primary.provider, primary.model)
            if args.json:
                _json({"ok": True, "provider": primary.provider, "reply": text})
            else:
                print(text)
            return 0
    return 1


def cmd_slots_add(args: argparse.Namespace) -> int:
    """Register a new API Pocket slot — immediately callable via `slots call`
    without any per-vendor SDK. See app/services/api_slot_registry.py."""
    from app.services.api_slot_registry import add_slot

    headers: dict[str, str] = {}
    for h in args.header or []:
        if ":" in h:
            k, v = h.split(":", 1)
            headers[k.strip()] = v.strip()

    try:
        result = add_slot(
            slot_id=args.id,
            category=args.category,
            base_url=args.base_url,
            auth_env_key=args.auth_env_key,
            auth_style=args.auth_style,
            openapi_url=args.openapi_url,
            method=args.method,
            path_template=args.path,
            headers=headers or None,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.json:
        _json(result)
    else:
        print(f"{result['id']}: registered ({result['category']}, auth={result['auth_env_key']})")
        if result.get("warning"):
            print(f"warning: {result['warning']}", file=sys.stderr)
    return 0


def cmd_slots_list(args: argparse.Namespace) -> int:
    from app.services.api_slot_registry import list_slots

    rows = list_slots()
    if args.json:
        _json(rows)
        return 0
    for row in rows:
        print(f"{row['id']:<20} {row['category']:<14} auth={row['auth_env_key']:<28} {row.get('base_url') or ''}")
    return 0


def cmd_slots_show(args: argparse.Namespace) -> int:
    from app.services.api_slot_registry import get_slot

    slot = get_slot(args.id)
    if slot is None:
        print(f"{args.id}: not found", file=sys.stderr)
        return 1
    if args.json:
        _json(slot)
    else:
        for k, v in slot.items():
            print(f"{k}: {v}")
    return 0


def cmd_slots_call(args: argparse.Namespace) -> int:
    """Generic REST forward through a registered slot — the TUI contract:
    stable exit codes, --json everywhere, human errors on stderr."""
    from app.services.api_slot_registry import call_slot

    body = None
    if args.body:
        try:
            body = json.loads(args.body)
        except json.JSONDecodeError as e:
            print(f"--body is not valid JSON: {e}", file=sys.stderr)
            return 1

    result = call_slot(
        args.id,
        body=body,
        method=args.method or None,
        path=args.path or None,
        timeout=args.timeout,
    )
    if args.json:
        _json(result)
    else:
        print(result)
    return 0 if result.get("ok") else 1


def cmd_slots_remove(args: argparse.Namespace) -> int:
    from app.services.api_slot_registry import remove_slot

    ok = remove_slot(args.id)
    if args.json:
        _json({"ok": ok})
    else:
        print(f"{args.id}: {'removed' if ok else 'not found'}")
    return 0 if ok else 1


def cmd_slots_suggest(args: argparse.Namespace) -> int:
    """Classify pasted key/URL/curl text into a slot suggestion — does not
    persist anything; pipe the result into `slots add` once it looks right."""
    from app.services.api_slot_registry import suggest_slot

    text = args.text
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read()
    text = (text or "").strip()
    if not text:
        print("No input given — pass text as an argument or pipe via stdin", file=sys.stderr)
        return 1

    result = suggest_slot(text, page_url=args.page_url, id_override=args.id)
    if args.json:
        _json(result)
    else:
        print(result)
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

    lc = llm_sub.add_parser("clear", help="Clear a provider's exhaustion mark (escape hatch for a bad classification)")
    lc.add_argument("provider")
    lc.set_defaults(func=cmd_llm_clear)

    lask = llm_sub.add_parser("ask", help="Like `ask`, but sticky + auto-cycles providers on quota exhaustion")
    lask.add_argument("prompt", nargs="?", default="", help="Prompt text (omit to read stdin)")
    lask.add_argument("--system", default="", help="Optional system prompt")
    lask.add_argument("-p", "--provider", default="", help="Force a specific provider for this call")
    lask.add_argument("-m", "--model", default="", help="Override model id")
    lask.add_argument("--max-tokens", type=int, default=600)
    lask.add_argument("--temperature", type=float, default=0.7)
    lask.add_argument("--timeout", type=float, default=90.0)
    lask.add_argument("--json", action="store_true", help="JSON output instead of raw text")
    lask.add_argument(
        "--prefer-uncensored", action="store_true",
        help="Opt-in: bias model pick toward dolphin/hermes/abliterated/heretic-named models when available. Off by default.",
    )
    lask.set_defaults(func=cmd_llm_ask)

    ltui = llm_sub.add_parser("tui", help="Interactive terminal viewer over the model/provider index (needs textual)")
    ltui.set_defaults(func=cmd_llm_tui)

    lmodels = llm_sub.add_parser("models", help="List cached models (master catalog) for one or all providers")
    lmodels.add_argument("provider", nargs="?", default=None)
    lmodels.add_argument("--json", action="store_true")
    lmodels.set_defaults(func=cmd_llm_models)

    lkeys = llm_sub.add_parser("keys", help="Manage stored API keys / custom provider endpoints")
    lkeys_sub = lkeys.add_subparsers(dest="llm_keys_cmd", required=True)

    lka = lkeys_sub.add_parser(
        "add", help="Store a key for a provider (built-in override, or register a new custom/HuggingFace-style endpoint)"
    )
    lka.add_argument("provider", help="Built-in provider id, or a new id for a custom endpoint")
    lka.add_argument("--base-url", default="", help="Required when registering a new custom provider")
    lka.set_defaults(func=cmd_llm_keys_add)

    lkl = lkeys_sub.add_parser("list", help="Show which providers have a key configured (never prints the key itself)")
    lkl.add_argument("--json", action="store_true")
    lkl.set_defaults(func=cmd_llm_keys_list)

    lkr = lkeys_sub.add_parser("remove", help="Delete a stored key (falls back to env var for built-ins, if any)")
    lkr.add_argument("provider")
    lkr.set_defaults(func=cmd_llm_keys_remove)

    research = sub.add_parser("research", help="RSS/Atom research scanner (Hermes-delivered)")
    research_sub = research.add_subparsers(dest="research_cmd", required=True)
    rs = research_sub.add_parser(
        "scan", help="Fetch sources, dedupe, batch-match new dev-lane items against SPRINT_STATE"
    )
    rs.add_argument("--seed", action="store_true", help="Populate dedupe only — skip the LLM match pass")
    rs.add_argument("--dry-run", action="store_true", help="Fetch + match but write nothing to the local index")
    rs.add_argument("--timeout", type=float, default=20.0, help="Per-source fetch timeout (seconds)")
    rs.add_argument("--json", action="store_true")
    rs.set_defaults(func=cmd_research_scan)

    slots = sub.add_parser("slots", help="API Pocket — PC-local REST service-slot registry")
    slots_sub = slots.add_subparsers(dest="slots_cmd", required=True)

    sa = slots_sub.add_parser("add", help="Register a new API slot")
    sa.add_argument("--id", default="", help="Slot id (default: derived from base URL / auth env key)")
    sa.add_argument("--category", default="generic-rest", choices=["llm", "text-format", "media", "generic-rest"])
    sa.add_argument("--base-url", default="", help="API base URL")
    sa.add_argument("--auth-env-key", required=True, help="Env var name holding the API key")
    sa.add_argument("--auth-style", default="bearer", choices=["bearer", "x-api-key", "query", "none"])
    sa.add_argument("--openapi-url", default="", help="Optional OpenAPI spec URL to infer a call path")
    sa.add_argument("--method", default="GET")
    sa.add_argument("--path", default="", help="Path template appended to base URL on call")
    sa.add_argument("--header", action="append", help="Extra static header 'Name: value' (repeatable)")
    sa.add_argument("--json", action="store_true")
    sa.set_defaults(func=cmd_slots_add)

    sl = slots_sub.add_parser("list", help="List registered slots")
    sl.add_argument("--json", action="store_true")
    sl.set_defaults(func=cmd_slots_list)

    ssh = slots_sub.add_parser("show", help="Show one slot's stored config")
    ssh.add_argument("id")
    ssh.add_argument("--json", action="store_true")
    ssh.set_defaults(func=cmd_slots_show)

    sc = slots_sub.add_parser("call", help="Call a registered slot")
    sc.add_argument("id")
    sc.add_argument("--body", default="", help="JSON request body")
    sc.add_argument("--method", default="", help="Override the slot's stored method")
    sc.add_argument("--path", default="", help="Override the slot's stored path template")
    sc.add_argument("--timeout", type=float, default=20.0)
    sc.add_argument("--json", action="store_true")
    sc.set_defaults(func=cmd_slots_call)

    sr = slots_sub.add_parser("remove", help="Delete a registered slot")
    sr.add_argument("id")
    sr.add_argument("--json", action="store_true")
    sr.set_defaults(func=cmd_slots_remove)

    ssg = slots_sub.add_parser("suggest", help="Classify pasted key/URL/curl text into a slot suggestion")
    ssg.add_argument("text", nargs="?", default="", help="Pasted text (omit to read stdin)")
    ssg.add_argument("--page-url", default="", help="Browser page URL context, if known")
    ssg.add_argument("--id", default="", help="Force a specific slot id in the suggestion")
    ssg.add_argument("--json", action="store_true")
    ssg.set_defaults(func=cmd_slots_suggest)

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
