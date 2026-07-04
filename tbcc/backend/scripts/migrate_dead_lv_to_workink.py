#!/usr/bin/env python3
"""
Emergency migration: replace dead Linkvertise (link-center.net) URLs with Work.ink.

Linkvertise often shadow-removes adult / Telegram targets while the dashboard still
shows posts as Active. This script re-wraps every LV URL in scheduled posts, loot
modifiers, and promo links using destinations from |dest= notes, dynamic ?r= decode,
legacy slug map, or (optional) bypass.vip.

  cd tbcc/backend
  py -3.13 scripts/migrate_dead_lv_to_workink.py              # dry-run report
  py -3.13 scripts/migrate_dead_lv_to_workink.py --execute
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.models.loot import LootModifier
from app.models.promo_affiliate_link import PromoAffiliateLink
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.link_gate_migrate import replace_linkvertise_urls_in_text, rewrap_linkvertise_gate
from app.services.link_gate_provider import PROVIDER_WORKINK, is_linkvertise_host

_URL_RE = re.compile(r"https?://[^\s\]\)<>\"']+", re.I)


def _urls_in(s: str | None) -> list[str]:
    if not s:
        return []
    return list(dict.fromkeys(_URL_RE.findall(s)))


def migrate(*, execute: bool, provider: str, try_bypass: bool) -> dict:
    report: dict = {"provider": provider, "changes": [], "failed": [], "tables": {}}
    db = SessionLocal()
    try:
        # --- loot modifiers ---
        lm_stats = {"rows": 0, "updated": 0, "failed": 0}
        for row in db.query(LootModifier).filter(LootModifier.active.is_(True)).all():
            lm_stats["rows"] += 1
            url = (row.target_url or "").strip().split()[0]
            if not is_linkvertise_host(url):
                continue
            new = rewrap_linkvertise_gate(
                url,
                provider=provider,
                source_note=row.source_note,
                try_bypass=try_bypass,
            )
            if not new:
                lm_stats["failed"] += 1
                report["failed"].append(
                    {"table": "loot_modifiers", "id": row.id, "label": row.label, "url": url}
                )
                continue
            if new != url:
                report["changes"].append(
                    {"table": "loot_modifiers", "id": row.id, "label": row.label, "from": url, "to": new}
                )
                if execute:
                    row.target_url = new
                    lm_stats["updated"] += 1
        report["tables"]["loot_modifiers"] = lm_stats

        # --- scheduled posts ---
        sp_stats = {"rows": 0, "updated": 0}
        for row in db.query(ScheduledTextPost).all():
            sp_stats["rows"] += 1
            changed = False
            content = row.content or ""
            new_content, ch = replace_linkvertise_urls_in_text(content, provider=provider, try_bypass=try_bypass)
            if ch:
                changed = True
                report["changes"].extend(
                    {"table": "scheduled_text_posts", "id": row.id, "field": "content", **c} for c in ch
                )

            new_vars = row.content_variations
            if row.content_variations:
                try:
                    vars_list = json.loads(row.content_variations)
                    if isinstance(vars_list, list):
                        out_vars = []
                        for v in vars_list:
                            if isinstance(v, str):
                                w, ch = replace_linkvertise_urls_in_text(v, provider=provider, try_bypass=try_bypass)
                                if ch:
                                    changed = True
                                    report["changes"].extend(
                                        {"table": "scheduled_text_posts", "id": row.id, "field": "var", **c}
                                        for c in ch
                                    )
                                out_vars.append(w)
                            else:
                                out_vars.append(v)
                        if changed:
                            new_vars = json.dumps(out_vars)
                except json.JSONDecodeError:
                    pass

            new_buttons = row.buttons
            if row.buttons:
                try:
                    btns = json.loads(row.buttons)
                    if isinstance(btns, list):
                        for row_btns in btns:
                            if not isinstance(row_btns, list):
                                continue
                            for b in row_btns:
                                if not isinstance(b, dict):
                                    continue
                                u = (b.get("url") or "").strip()
                                if not is_linkvertise_host(u):
                                    continue
                                new = rewrap_linkvertise_gate(u, provider=provider, try_bypass=try_bypass)
                                if new and new != u:
                                    b["url"] = new
                                    changed = True
                                    report["changes"].append(
                                        {
                                            "table": "scheduled_text_posts",
                                            "id": row.id,
                                            "field": "button",
                                            "from": u,
                                            "to": new,
                                        }
                                    )
                        if changed:
                            new_buttons = json.dumps(btns)
                except json.JSONDecodeError:
                    pass

            if execute and changed:
                row.content = new_content
                row.content_variations = new_vars
                row.buttons = new_buttons
                sp_stats["updated"] += 1
        report["tables"]["scheduled_text_posts"] = sp_stats

        # --- promo affiliate short URLs ---
        promo_stats = {"rows": 0, "updated": 0}
        for row in db.query(PromoAffiliateLink).all():
            promo_stats["rows"] += 1
            for field in ("short_url", "url"):
                raw = (getattr(row, field) or "").strip()
                if not raw:
                    continue
                u = raw.split()[0]
                if not is_linkvertise_host(u):
                    continue
                new = rewrap_linkvertise_gate(u, provider=provider, try_bypass=try_bypass)
                if new and new != u:
                    report["changes"].append(
                        {"table": "promo_affiliate_links", "id": row.id, "field": field, "from": u, "to": new}
                    )
                    if execute:
                        setattr(row, field, new)
                        promo_stats["updated"] += 1
        report["tables"]["promo_affiliate_links"] = promo_stats

        if execute:
            db.commit()
    finally:
        db.close()

    report["summary"] = {
        "changes": len(report["changes"]),
        "failed": len(report["failed"]),
    }
    return report


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Migrate dead Linkvertise URLs to Work.ink")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--provider", default=PROVIDER_WORKINK)
    p.add_argument(
        "--try-bypass",
        action="store_true",
        help="Use bypass.vip when slug/dest note unavailable (slow, needs BYPASS_API_KEY)",
    )
    args = p.parse_args()
    r = migrate(execute=args.execute, provider=args.provider.strip().lower(), try_bypass=args.try_bypass)
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
