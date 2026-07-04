"""
Wrap URLs in text/files with link gate providers (Linkvertise, LootLabs, AdMaven, Work.ink).

Examples (from tbcc/backend):
  py -3.13 scripts/wrap_linkvertise.py --list-providers
  py -3.13 scripts/wrap_linkvertise.py --preview --text-file ../../docs/samples/aof_links_hub.txt
  py -3.13 scripts/wrap_linkvertise.py --provider lootlabs --url "https://t.me/+4umB83be5n41MmEx"
  py -3.13 scripts/wrap_linkvertise.py --text-file hub.txt --out hub_wrapped.txt --import-promo
  py -3.13 scripts/wrap_linkvertise.py --scheduled-post-id 3 --dry-run
  py -3.13 scripts/wrap_linkvertise.py --scheduled-post-id 3 --execute
  py -3.13 scripts/wrap_linkvertise.py --campaign-group-id 87ed6454-... --text-file ../docs/samples/aof_links_hub_scheduler.txt --execute --interval-minutes 480 --pin-after-send --random-channel
  py -3.13 scripts/wrap_linkvertise.py --json scripts/promo_bulk_import_adultforce.json --include-affiliates --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

import httpx

from app.database.session import SessionLocal
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.link_gate_provider import configured_gate_providers
from app.services.linkvertise_wrap import (
    decide_wrap,
    decisions_to_promo_items,
    publisher_id_from_env,
    wrap_scheduled_post_content,
    wrap_urls_in_text,
)

def _api_base() -> str:
    import os

    return (os.getenv("TBCC_API_URL") or "http://127.0.0.1:8000").rstrip("/")


def _wrap_kwargs(args: argparse.Namespace) -> dict:
    kw = {
        "include_affiliates": bool(args.include_affiliates),
        "include_public_telegram": not args.invites_only,
        "include_mega_hosts": bool(args.include_mega),
    }
    if args.provider and args.provider != "rotate":
        kw["provider"] = args.provider.strip().lower()
    return kw


def _print_decisions(decisions: list) -> None:
    wrapped = sum(1 for d in decisions if d.wrapped)
    skipped = len(decisions) - wrapped
    print(f"URLs: {len(decisions)} found, {wrapped} wrapped, {skipped} skipped", file=sys.stderr)
    for d in decisions:
        mark = "WRAP" if d.wrapped else "SKIP"
        prov = f" [{d.provider}]" if getattr(d, "provider", None) else ""
        print(f"  [{mark}]{prov} {d.reason}: {d.original[:90]}", file=sys.stderr)
        if d.wrapped:
            print(f"         -> {d.wrapped[:100]}", file=sys.stderr)


def _import_promo(items: list[dict]) -> None:
    if not items:
        print("No promo items to import.", file=sys.stderr)
        return
    url = f"{_api_base()}/promo-affiliate-links/bulk"
    with httpx.Client(timeout=30.0) as client:
        r = client.post(url, json={"items": items})
    r.raise_for_status()
    print(f"Imported {r.json().get('created', len(items))} promo rows via API.", file=sys.stderr)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="Wrap eligible URLs with a link gate provider")
    p.add_argument(
        "--provider",
        choices=("linkvertise", "lootlabs", "admaven", "workink", "rotate"),
        help="Gate provider (default: TBCC_LINK_GATE_PROVIDERS rotation)",
    )
    p.add_argument("--list-providers", action="store_true", help="Print configured gate providers and exit")
    p.add_argument("--url", help="Single URL to wrap")
    p.add_argument("--label", help="Promo label when using --url with --import-promo")
    p.add_argument("--text-file", type=Path, help="Input text/markdown file")
    p.add_argument("--out", type=Path, help="Write wrapped text here (default: stdout)")
    p.add_argument("--json", type=Path, help="TBCC bulk JSON {items:[{url,label,...}]} — wrap url + set short_url")
    p.add_argument("--scheduled-post-id", type=int, help="TBCC scheduled_text_posts.id to rewrite")
    p.add_argument("--campaign-group-id", help="Update all rows in a multi-channel campaign (UUID)")
    p.add_argument("--interval-minutes", type=int, help="With --campaign-group-id: set recurring interval")
    p.add_argument("--pin-after-send", action="store_true", help="Pin Telegram message after each send")
    p.add_argument("--random-channel", action="store_true", help="One random channel per interval tick")
    p.add_argument("--reset-send-state", action="store_true", help="Clear sent_at / last_posted_at (fresh recurring run)")
    p.add_argument("--execute", action="store_true", help="Apply DB/API changes (default is dry-run)")
    p.add_argument("--dry-run", action="store_true", help="Explicit dry-run (default unless --execute)")
    p.add_argument("--import-promo", action="store_true", help="POST wrapped pairs to promo-affiliate-links/bulk")
    p.add_argument("--preview", action="store_true", help="Alias for dry-run + print wrapped text")
    p.add_argument("--include-affiliates", action="store_true", help="Also wrap AdultForce/PPS/affiliate URLs (usually a bad idea)")
    p.add_argument("--include-mega", action="store_true", help="Wrap file host URLs (mega, pixeldrain, etc.)")
    p.add_argument("--invites-only", action="store_true", help="Only t.me/+ and addlist (skip @channel public links)")
    args = p.parse_args()

    dry_run = args.preview or args.dry_run or not args.execute
    if args.execute:
        dry_run = False

    if args.list_providers:
        provs = configured_gate_providers()
        print("Configured gate providers:", ", ".join(provs) if provs else "(none)")
        raise SystemExit(0 if provs else 2)

    provider = None
    if args.provider and args.provider != "rotate":
        provider = args.provider

    pub = None
    need_lv = not provider or provider == "linkvertise"
    if need_lv:
        try:
            pub = publisher_id_from_env()
        except ValueError as e:
            if not provider:
                provs = configured_gate_providers()
                if not provs:
                    print(f"Error: {e}", file=sys.stderr)
                    raise SystemExit(2)
            else:
                print(f"Error: {e}", file=sys.stderr)
                raise SystemExit(2)

    kwargs = _wrap_kwargs(args)
    if provider:
        kwargs["provider"] = provider

    if args.url:
        d = decide_wrap(args.url, pub, **kwargs)
        _print_decisions([d])
        if d.wrapped:
            print(d.wrapped)
            if args.import_promo and not dry_run:
                label = (args.label or "lv-single")[:512]
                _import_promo(
                    [
                        {
                            "label": label,
                            "url": d.original,
                            "short_url": d.wrapped,
                            "payout_kind": d.provider or "linkvertise",
                            "payout_detail": d.reason,
                            "priority_tier": 15,
                            "active": True,
                        }
                    ]
                )
        return

    if args.text_file:
        text = args.text_file.read_text(encoding="utf-8")
        wrapped, decisions = wrap_urls_in_text(text, pub, **kwargs)
        _print_decisions(decisions)
        if args.out:
            if dry_run:
                print(f"Dry-run: would write {args.out}", file=sys.stderr)
            else:
                args.out.write_text(wrapped, encoding="utf-8")
                print(f"Wrote {args.out}", file=sys.stderr)
        else:
            print(wrapped)
        if args.import_promo and not dry_run:
            _import_promo(decisions_to_promo_items(decisions))
        return

    if args.json:
        payload = json.loads(args.json.read_text(encoding="utf-8"))
        items_in = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items_in, list):
            print("JSON must be {items: [...]}", file=sys.stderr)
            raise SystemExit(2)
        out_items: list[dict] = []
        decisions = []
        for row in items_in:
            if not isinstance(row, dict):
                continue
            raw_url = str(row.get("url") or "").strip()
            if not raw_url:
                continue
            d = decide_wrap(raw_url, pub, **kwargs)
            decisions.append(d)
            new_row = dict(row)
            if d.wrapped:
                new_row["url"] = d.original
                new_row["short_url"] = d.wrapped
                new_row["payout_kind"] = d.provider or "linkvertise"
                new_row.setdefault("payout_detail", d.reason)
            out_items.append(new_row)
        _print_decisions(decisions)
        out_path = args.out or args.json.with_name(args.json.stem + "_wrapped.json")
        if dry_run:
            print(f"Dry-run: would write {out_path}", file=sys.stderr)
        else:
            out_path.write_text(json.dumps({"items": out_items}, indent=2) + "\n", encoding="utf-8")
            print(f"Wrote {out_path}", file=sys.stderr)
        if args.import_promo and not dry_run:
            _import_promo(out_items)
        return

    if args.campaign_group_id:
        text_src = ""
        if args.text_file:
            text_src = args.text_file.read_text(encoding="utf-8")
        else:
            print("Error: --campaign-group-id requires --text-file", file=sys.stderr)
            raise SystemExit(2)
        wrapped, decisions = wrap_urls_in_text(text_src, pub, **_wrap_kwargs(args))
        _print_decisions(decisions)
        db = SessionLocal()
        try:
            rows = (
                db.query(ScheduledTextPost)
                .filter(ScheduledTextPost.campaign_group_id == args.campaign_group_id)
                .order_by(ScheduledTextPost.id)
                .all()
            )
            if not rows:
                print(f"No rows for campaign {args.campaign_group_id}", file=sys.stderr)
                raise SystemExit(1)
            print(f"Campaign rows: {len(rows)} (leader id={rows[0].id})", file=sys.stderr)
            if dry_run:
                print(f"Dry-run: would set content ({len(wrapped)} chars), interval={args.interval_minutes}", file=sys.stderr)
                print(wrapped[:1200])
                if len(wrapped) > 1200:
                    print("\n... [truncated]", file=sys.stderr)
            else:
                for p in rows:
                    p.content = wrapped
                    p.content_variations = None
                    if args.interval_minutes is not None:
                        p.interval_minutes = int(args.interval_minutes)
                        p.sent_at = None
                    if args.reset_send_state or args.interval_minutes is not None:
                        p.sent_at = None
                        p.last_posted_at = None
                    if args.pin_after_send:
                        p.pin_after_send = True
                    if args.random_channel:
                        p.campaign_random_channel = True
                db.commit()
                print(f"Updated campaign {args.campaign_group_id} ({len(rows)} rows)", file=sys.stderr)
        finally:
            db.close()
        if args.import_promo and not dry_run:
            _import_promo(decisions_to_promo_items(decisions))
        return

    if args.scheduled_post_id:
        db = SessionLocal()
        try:
            row = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == args.scheduled_post_id).first()
            if not row:
                print(f"No scheduled post id={args.scheduled_post_id}", file=sys.stderr)
                raise SystemExit(1)
            new_content, new_vars, decisions = wrap_scheduled_post_content(
                row.content or "",
                row.content_variations,
                pub,
                **kwargs,
            )
            _print_decisions(decisions)
            if dry_run:
                print("\n--- wrapped content preview ---\n", file=sys.stderr)
                print(new_content[:4000])
                if len(new_content) > 4000:
                    print("\n... [truncated]", file=sys.stderr)
            else:
                row.content = new_content
                if new_vars is not None:
                    row.content_variations = new_vars
                db.commit()
                print(f"Updated scheduled post id={row.id}", file=sys.stderr)
        finally:
            db.close()
        return

    p.print_help()
    print("\nProvide --url, --text-file, --json, or --scheduled-post-id", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
