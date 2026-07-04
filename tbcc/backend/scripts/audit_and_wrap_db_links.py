"""Audit TBCC DB for http(s) links; wrap with Linkvertise and/or obfuscate bare LV URLs as HTML anchors."""
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
from app.models.promo_affiliate_link import PromoAffiliateLink
from app.models.scheduled_text_post import ScheduledTextPost
from app.models.subscription_plan import SubscriptionPlan
from app.models.loot import LootModifier, LootPoolEligibility
from app.models.channel import Channel
from app.models.caption_snippet import CaptionSnippet
from app.services.linkvertise_hyperlink import (
    count_bare_lv_urls,
    obfuscate_bare_lv_urls_in_text,
)
from app.services.linkvertise_wrap import (
    classify_url,
    decide_wrap,
    publisher_id_from_env,
    wrap_urls_in_text,
)

_URL_RE = re.compile(r"https?://[^\s\]\)<>\"']+", re.I)


def _urls_in(s: str | None) -> list[str]:
    if not s:
        return []
    return list(dict.fromkeys(_URL_RE.findall(s)))


def _hyperlink_field(text: str | None) -> tuple[str, int]:
    if not text:
        return text or "", 0
    before = count_bare_lv_urls(text)
    if before == 0:
        return text, 0
    new_text, _changes = obfuscate_bare_lv_urls_in_text(text)
    return new_text, before


def audit(execute: bool, include_affiliates: bool, *, hyperlink_lv: bool = False) -> dict:
    pub = publisher_id_from_env()
    report: dict = {"wrapped": [], "skipped": [], "hyperlinks": [], "tables": {}}
    db = SessionLocal()
    try:
        # --- scheduled posts ---
        sp_stats = {"rows": 0, "updated": 0}
        for row in db.query(ScheduledTextPost).all():
            sp_stats["rows"] += 1
            fields: dict[str, str] = {"content": row.content or ""}
            if row.content_variations:
                try:
                    vars_list = json.loads(row.content_variations)
                    if isinstance(vars_list, list):
                        for i, v in enumerate(vars_list):
                            if isinstance(v, str):
                                fields[f"var_{i}"] = v
                except json.JSONDecodeError:
                    pass
            if row.buttons:
                try:
                    btns = json.loads(row.buttons)
                    if isinstance(btns, list):
                        fields["buttons"] = json.dumps(btns)
                except json.JSONDecodeError:
                    pass
            changed = False
            new_content = row.content or ""
            new_vars = row.content_variations
            new_buttons = row.buttons

            if row.content and _urls_in(row.content):
                new_content, dec = wrap_urls_in_text(
                    row.content, pub, include_affiliates=include_affiliates
                )
                if new_content != row.content:
                    changed = True
                    for d in dec:
                        (report["wrapped"] if d.wrapped else report["skipped"]).append(
                            {"table": "scheduled_text_posts", "id": row.id, "field": "content", **d.__dict__}
                        )

            if row.content_variations:
                try:
                    vars_list = json.loads(row.content_variations)
                    if isinstance(vars_list, list):
                        out_vars = []
                        for v in vars_list:
                            if isinstance(v, str):
                                w, dec = wrap_urls_in_text(v, pub, include_affiliates=include_affiliates)
                                out_vars.append(w)
                                for d in dec:
                                    if d.wrapped:
                                        changed = True
                            else:
                                out_vars.append(v)
                        if changed:
                            new_vars = json.dumps(out_vars)
                except json.JSONDecodeError:
                    pass

            if row.buttons:
                try:
                    btns = json.loads(row.buttons)
                    if isinstance(btns, list):
                        for b in btns:
                            if isinstance(b, dict) and b.get("url"):
                                d = decide_wrap(str(b["url"]), pub, include_affiliates=include_affiliates)
                                if d.wrapped:
                                    b["url"] = d.wrapped
                                    changed = True
                        if changed:
                            new_buttons = json.dumps(btns)
                except json.JSONDecodeError:
                    pass

            if hyperlink_lv:
                hc, n = _hyperlink_field(new_content)
                if n:
                    changed = True
                    new_content = hc
                    report["hyperlinks"].append(
                        {"table": "scheduled_text_posts", "id": row.id, "field": "content", "count": n}
                    )
                if new_vars:
                    try:
                        vars_list = json.loads(new_vars)
                        if isinstance(vars_list, list):
                            out_vars = []
                            for v in vars_list:
                                if isinstance(v, str):
                                    hv, vn = _hyperlink_field(v)
                                    if vn:
                                        changed = True
                                        v = hv
                                    out_vars.append(v)
                                else:
                                    out_vars.append(v)
                            new_vars = json.dumps(out_vars)
                    except json.JSONDecodeError:
                        pass

            if execute and changed:
                row.content = new_content
                row.content_variations = new_vars
                row.buttons = new_buttons
                sp_stats["updated"] += 1
        report["tables"]["scheduled_text_posts"] = sp_stats

        # --- promo affiliate links ---
        promo_stats = {"rows": 0, "short_url_set": 0}
        for row in db.query(PromoAffiliateLink).all():
            promo_stats["rows"] += 1
            url = (row.url or "").strip()
            if not url.startswith("http"):
                continue
            short = (row.short_url or "").strip()
            action, reason = classify_url(url, include_affiliates=include_affiliates)
            if action != "wrap":
                continue
            d = decide_wrap(url, pub, include_affiliates=include_affiliates)
            if not d.wrapped:
                continue
            if short == d.wrapped:
                promo_stats["short_url_set"] += 1
                continue
            if execute:
                if not short or not short.startswith("http"):
                    row.short_url = d.wrapped
                promo_stats["short_url_set"] += 1
                report["wrapped"].append(
                    {"table": "promo_affiliate_links", "id": row.id, "label": row.label, "wrapped": d.wrapped}
                )
        report["tables"]["promo_affiliate_links"] = promo_stats

        # --- loot modifiers ---
        lm_stats = {"rows": 0, "updated": 0}
        for row in db.query(LootModifier).filter(LootModifier.active.is_(True)).all():
            lm_stats["rows"] += 1
            url = (row.target_url or "").strip()
            if not url.startswith("http"):
                continue
            d = decide_wrap(url, pub, include_affiliates=include_affiliates, include_mega_hosts=True)
            if d.wrapped and d.wrapped != url:
                if execute:
                    row.target_url = d.wrapped
                    lm_stats["updated"] += 1
                report["wrapped"].append(
                    {"table": "loot_modifiers", "id": row.id, "label": row.label, "kind": row.kind}
                )
        report["tables"]["loot_modifiers"] = lm_stats

        # --- subscription plans (descriptions only; not affiliate checkout URLs) ---
        plan_stats = {"rows": 0, "active": 0, "updated": 0}
        plans = db.query(SubscriptionPlan).all()
        for row in plans:
            plan_stats["rows"] += 1
            if row.is_active:
                plan_stats["active"] += 1
            if not hyperlink_lv:
                continue
            changed = False
            desc = row.description or ""
            new_desc, n = _hyperlink_field(desc)
            if n:
                changed = True
                row.description = new_desc
                report["hyperlinks"].append(
                    {"table": "subscription_plans", "id": row.id, "field": "description", "count": n}
                )
            vars_col = getattr(row, "description_variations_json", None)
            if vars_col:
                try:
                    vars_list = json.loads(vars_col)
                    if isinstance(vars_list, list):
                        out_vars = []
                        for v in vars_list:
                            if isinstance(v, str):
                                hv, vn = _hyperlink_field(v)
                                if vn:
                                    changed = True
                                    v = hv
                                out_vars.append(v)
                            else:
                                out_vars.append(v)
                        if changed:
                            row.description_variations_json = json.dumps(out_vars)
                except json.JSONDecodeError:
                    pass
            if execute and changed:
                plan_stats["updated"] += 1

        # --- caption snippets ---
        snip_stats = {"rows": 0, "updated": 0}
        for row in db.query(CaptionSnippet).all():
            snip_stats["rows"] += 1
            body = (row.body or "") if hasattr(row, "body") else (row.content or "")
            if not body:
                continue
            new_body, dec = wrap_urls_in_text(body, pub, include_affiliates=include_affiliates)
            if hyperlink_lv:
                new_body, hn = _hyperlink_field(new_body)
                if hn:
                    report["hyperlinks"].append({"table": "caption_snippets", "id": row.id, "count": hn})
            if new_body != body:
                if execute:
                    if hasattr(row, "body"):
                        row.body = new_body
                    else:
                        row.content = new_body
                    snip_stats["updated"] += 1
                for d in dec:
                    if d.wrapped:
                        report["wrapped"].append({"table": "caption_snippets", "id": row.id})
        report["tables"]["caption_snippets"] = snip_stats

        report["tables"]["subscription_plans"] = plan_stats
        report["subscription_plans"] = [
            {
                "id": p.id,
                "name": p.name,
                "active": p.is_active,
                "bot_section": p.bot_section,
                "price_stars": p.price_stars,
                "product_type": p.product_type,
                "nowpayments_price_usd": p.nowpayments_price_usd,
                "channel_id": p.channel_id,
            }
            for p in plans
        ]

        # --- pools / loot eligibility ---
        pools = db.query(LootPoolEligibility).all()
        report["loot_pool_eligibility"] = len(pools)
        report["channels"] = [
            {"id": c.id, "name": c.name, "identifier": c.identifier}
            for c in db.query(Channel).order_by(Channel.id).all()
        ]

        if execute:
            db.commit()
    finally:
        db.close()
    return report


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("--execute", action="store_true")
    p.add_argument("--include-affiliates", action="store_true")
    p.add_argument(
        "--hyperlink-lv",
        action="store_true",
        help="Replace bare link-center.net / Linkvertise URLs with Telegram HTML <a href> anchors",
    )
    args = p.parse_args()
    r = audit(
        execute=args.execute,
        include_affiliates=args.include_affiliates,
        hyperlink_lv=args.hyperlink_lv,
    )
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
