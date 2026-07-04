#!/usr/bin/env python3
"""Provision Linkvertise Post & earn dashboard slugs for pack-pool modifiers (Playwright).

Workflow:
  1. --login     Save publisher session (once)
  2. --record     Record Post & earn click path → fill selectors in flow config
  3. --dry-run    List modifiers missing gate_lv
  4. --execute    Create dashboard links + update loot_modifiers.source_note

Install: py -m pip install playwright && py -m playwright install chromium
Record (Brave): py scripts/linkvertise_codegen.py --save-storage .linkvertise-auth.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.models.loot import LootModifier
from app.services.linkvertise_dashboard_provision import (
    _spec,
    apply_lv_url_to_modifier,
    auth_state_path,
    create_dashboard_links_batch,
    flow_config_path,
    load_flow_config,
    login_and_save_session,
    modifier_needs_lv,
    probe_lv_gate,
    record_dashboard_flow,
    selectors_ready,
)
from app.services.playwright_browser import (
    browser_label,
    codegen_cli_command,
    describe_launch_mode,
    list_brave_profiles,
    resolve_launch_mode,
    use_brave_persistent_profile,
    default_brave_profile_name,
)
from app.services.loot_pack_pool import (
    PACK_POOL_SOURCE_MARKERS,
    auto_wire_packs_enabled,
    refresh_aof_packs_scheduler,
)


def _pack_pool_query(db):
    from sqlalchemy import or_

    q = db.query(LootModifier).filter(
        LootModifier.kind == "mega_pack",
        LootModifier.active.is_(True),
    )
    clauses = [LootModifier.source_note.like(f"%{m}%") for m in PACK_POOL_SOURCE_MARKERS]
    return q.filter(or_(*clauses)).order_by(LootModifier.id.asc())


def list_pending(db, limit: int | None = None, modifier_ids: list[int] | None = None) -> list[LootModifier]:
    rows = _pack_pool_query(db).all()
    pending = [m for m in rows if modifier_needs_lv(m)]
    if modifier_ids:
        wanted = {int(x) for x in modifier_ids}
        pending = [m for m in pending if m.id in wanted]
    if limit is not None:
        return pending[:limit]
    return pending


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
    print(f"Ad tasks:        {cfg.ad_tasks_count} (TBCC_LINKVERTISE_AD_TASKS / flow config)")
    print(f"Batch loop:      create_new_link between packs = {cfg.reuse_create_new_link_loop}")
    if not selectors_ready(cfg):
        missing = [
            k for k in ("create_link_button", "destination_input", "submit_button") if not _spec(cfg, k)
        ]
        print(f"  Missing locators: {', '.join(missing)}")
        print("  Import codegen: py scripts/import_linkvertise_codegen.py your_recording.py --ad-tasks 2")
    with SessionLocal() as db:
        try:
            pending = list_pending(db)
            print(f"Pending LV:      {len(pending)} pack(s)")
            for m in pending[:20]:
                print(f"  mod #{m.id}  {m.label[:60]}")
            if len(pending) > 20:
                print(f"  … and {len(pending) - 20} more")
        except Exception as e:
            print(f"Pending LV:      (DB unavailable: {e})")
    return 0


def cmd_dry_run(limit: int | None, modifier_ids: list[int] | None) -> int:
    with SessionLocal() as db:
        pending = list_pending(db, limit=limit, modifier_ids=modifier_ids)
        print(f"Would provision {len(pending)} modifier(s)")
        for m in pending:
            from app.services.aof_packs_post_copy import parse_pack_source_note

            meta = parse_pack_source_note(m.source_note)
            print(f"  #{m.id} dest={meta.destination_url or '?'} adm={bool(meta.gate_adm_url)}")
    return 0


def cmd_execute(limit: int | None, headed: bool, skip_probe: bool, modifier_ids: list[int] | None, keep_open: bool, no_close: bool) -> int:
    if not selectors_ready(load_flow_config()):
        print("ERROR: Flow not configured. Import codegen first.", file=sys.stderr)
        return 2
    auth = auth_state_path()
    launch_mode = resolve_launch_mode(storage_state=auth)
    if launch_mode == "session" and not auth.is_file() and not use_brave_persistent_profile() and not headed:
        print("ERROR: Auth state missing. Run --login --headed or set TBCC_BRAVE_PROFILE_NAME.", file=sys.stderr)
        return 2

    ok_count = 0
    with SessionLocal() as db:
        pending = list_pending(db, limit=limit, modifier_ids=modifier_ids)
        if not pending:
            print("Nothing pending.")
            return 0

        from app.services.aof_packs_post_copy import parse_pack_source_note

        work: list[tuple[LootModifier, str, str | None]] = []
        for mod in pending:
            meta = parse_pack_source_note(mod.source_note)
            dest = (meta.destination_url or "").strip()
            if not dest:
                print(f"  skip #{mod.id}: no destination_url")
                continue
            work.append((mod, dest, mod.label))

        if not work:
            return 1

        batch_items = [(dest, title) for _, dest, title in work]
        pack_ids = [mod.id for mod, _, _ in work]
        print(f"Batch provision {len(batch_items)} link(s) in one browser session (Create new link loop)")
        results = create_dashboard_links_batch(
            batch_items,
            headed=headed,
            keep_open=keep_open,
            no_close=no_close,
            pack_ids=pack_ids,
        )

        for (mod, dest, _title), (_d, _t, lv_or_err) in zip(work, results):
            if not lv_or_err or str(lv_or_err).startswith("ERROR:"):
                print(f"  FAIL #{mod.id}: {lv_or_err}")
                continue
            lv_url = str(lv_or_err)
            if not skip_probe:
                probe = probe_lv_gate(lv_url)
                print(f"  #{mod.id} {lv_url} probe={probe.get('flags')}")
                if not probe.get("ok"):
                    print("  WARN: probe did not confirm LV shell — storing anyway")
            else:
                print(f"  #{mod.id} {lv_url}")
            apply_lv_url_to_modifier(mod, lv_url)
            db.commit()
            ok_count += 1

        if ok_count and auto_wire_packs_enabled():
            refresh_aof_packs_scheduler(db)
            print("Refreshed AOF PACKS scheduler (TBCC_PACK_POOL_AUTO_WIRE=1)")

    print(f"Done: {ok_count}/{len(work)} provisioned")
    return 0 if ok_count else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Linkvertise dashboard slug provisioner for AOF pack pool")
    p.add_argument("--login", action="store_true", help="Open browser to log in; save session state")
    p.add_argument("--record", action="store_true", help="Open Post & earn with Inspector to record selectors")
    p.add_argument("--status", action="store_true", help="Show config + pending count")
    p.add_argument("--dry-run", action="store_true", help="List modifiers missing gate_lv")
    p.add_argument("--execute", action="store_true", help="Create dashboard links for pending modifiers")
    p.add_argument("--limit", type=int, default=None, help="Max modifiers per run")
    p.add_argument("--headed", action="store_true", help="Show browser during --execute")
    p.add_argument(
        "--keep-open",
        action="store_true",
        help="After --execute (headed), pause in Inspector before closing",
    )
    p.add_argument(
        "--no-close",
        action="store_true",
        help="Leave browser open after --execute until you close the window manually",
    )
    p.add_argument(
        "--auto-close",
        action="store_true",
        help="Close browser immediately when --execute finishes (overrides --headed default)",
    )
    p.add_argument("--skip-probe", action="store_true", help="Skip HTTP probe after each created link")
    p.add_argument("--modifier-id", type=int, action="append", default=None, help="Only these loot_modifiers ids (repeatable)")
    args = p.parse_args()
    mod_ids = args.modifier_id

    if args.login:
        login_and_save_session(headed=True)
        print("\nNext: py scripts/provision_linkvertise_dashboard_links.py --record")
        return 0
    if args.record:
        record_dashboard_flow(headed=True)
        print(
            "\n=== IMPORT CODEGEN ===\n"
            "Copy the Playwright codegen panel to a file (e.g. lv_recording.py), then:\n"
            "  py scripts/import_linkvertise_codegen.py lv_recording.py --ad-tasks 2\n"
            "Or save session from codegen (Brave via TBCC wrapper):\n"
            f"  {codegen_cli_command(save_storage=auth_state_path())}\n"
        )
        return 0
    if args.status:
        return cmd_status()
    if args.dry_run:
        return cmd_dry_run(args.limit, mod_ids)
    if args.execute:
        no_close = args.no_close or (args.headed and not args.auto_close)
        keep_open = args.keep_open or (args.headed and not args.no_close and not args.auto_close)
        return cmd_execute(args.limit, args.headed, args.skip_probe, mod_ids, keep_open, no_close)

    p.print_help()
    return cmd_status()


if __name__ == "__main__":
    raise SystemExit(main())
