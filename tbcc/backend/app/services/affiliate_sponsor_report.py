"""Admin report: all promo affiliate sponsors with clicks + attributed revenue."""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.click_link import ClickLink
from app.models.income_entry import IncomeEntry
from app.models.promo_affiliate_link import PromoAffiliateLink
from app.services.affiliate_payout_rail import RAIL_SORT_KEY, infer_payout_rail
from app.services.promo_affiliate_rotation import row_network_keys, row_placements

_SLUG_SAFE = re.compile(r"[^a-z0-9]+")


def _lab_slug(label: str) -> str:
    return _SLUG_SAFE.sub("-", (label or "aff").lower()).strip("-")[:14] or "aff"


def _lab_ref(label: str) -> str:
    return _SLUG_SAFE.sub("_", (label or "aff").lower()).strip("_")[:24] or "aff"


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _active_row(row: PromoAffiliateLink, *, now: datetime | None = None) -> bool:
    if not bool(row.active):
        return False
    exp = row.expires_at
    if exp is None:
        return True
    now = now or datetime.now(timezone.utc)
    exp_utc = exp.replace(tzinfo=timezone.utc) if exp.tzinfo is None else exp
    return exp_utc > now


def _click_stats_by_affiliate(db: Session) -> dict[str, Any]:
    """Index click_links for joining onto promo affiliates."""
    links = db.query(ClickLink).all()
    by_dest: dict[str, list[ClickLink]] = {}
    by_slug_prefix: dict[str, list[ClickLink]] = {}
    by_ref_prefix: dict[str, list[ClickLink]] = {}
    for link in links:
        dest = _normalize_url(link.destination_url or "")
        if dest:
            by_dest.setdefault(dest, []).append(link)
        slug = (link.slug or "").lower()
        ref = (link.source_ref or "").lower()
        if slug.startswith("aff-"):
            by_slug_prefix.setdefault(slug, []).append(link)
        if ref.startswith("src_aff_"):
            by_ref_prefix.setdefault(ref, []).append(link)
    return {
        "links": links,
        "by_dest": by_dest,
        "by_slug_prefix": by_slug_prefix,
        "by_ref_prefix": by_ref_prefix,
    }


def _sum_hits(links: list[ClickLink]) -> tuple[int, list[dict[str, Any]]]:
    seen: set[int] = set()
    total = 0
    details: list[dict[str, Any]] = []
    for link in links:
        lid = int(link.id or 0)
        if lid in seen:
            continue
        seen.add(lid)
        hits = int(link.hit_count or 0)
        total += hits
        details.append(
            {
                "slug": link.slug,
                "source_ref": link.source_ref,
                "hits": hits,
                "label": link.label,
                "destination_url": link.destination_url,
            }
        )
    details.sort(key=lambda d: -int(d["hits"]))
    return total, details


def _revenue_by_source_prefix(db: Session, *, days: int) -> dict[str, dict[str, Any]]:
    since = datetime.utcnow() - timedelta(days=max(1, min(366, days)))
    rows = (
        db.query(
            IncomeEntry.traffic_source_ref,
            func.coalesce(func.sum(IncomeEntry.amount_usd_cents), 0),
            func.count(IncomeEntry.id),
        )
        .filter(
            IncomeEntry.created_at >= since,
            IncomeEntry.traffic_source_ref.isnot(None),
            IncomeEntry.traffic_source_ref != "",
        )
        .group_by(IncomeEntry.traffic_source_ref)
        .all()
    )
    out: dict[str, dict[str, Any]] = {}
    for ref, cents, n in rows:
        key = (ref or "").strip()
        if not key:
            continue
        out[key] = {
            "usd_cents": int(cents or 0),
            "usd": round(int(cents or 0) / 100.0, 2),
            "entries": int(n or 0),
        }
    return out


def _match_revenue_for_label(
    rev_by_ref: dict[str, dict[str, Any]],
    *,
    label: str,
    beacon_details: list[dict[str, Any]],
) -> dict[str, Any]:
    lab = _lab_ref(label)
    prefix = f"src_aff_{lab}_"
    usd_cents = 0
    entries = 0
    matched_refs: list[str] = []
    for ref, data in rev_by_ref.items():
        if ref.startswith(prefix) or ref == f"src_aff_{lab}":
            usd_cents += int(data["usd_cents"])
            entries += int(data["entries"])
            matched_refs.append(ref)
    for d in beacon_details:
        ref = (d.get("source_ref") or "").strip()
        if ref and ref in rev_by_ref and ref not in matched_refs:
            usd_cents += int(rev_by_ref[ref]["usd_cents"])
            entries += int(rev_by_ref[ref]["entries"])
            matched_refs.append(ref)
    return {
        "usd_cents": usd_cents,
        "usd": round(usd_cents / 100.0, 2),
        "entries": entries,
        "source_refs": matched_refs,
    }


def collect_affiliate_sponsor_rows(
    db: Session,
    *,
    include_inactive: bool = False,
    revenue_days: int = 30,
) -> list[dict[str, Any]]:
    """One dict per promo_affiliate_links row with clicks + TBCC-attributed $."""
    click_idx = _click_stats_by_affiliate(db)
    rev_by_ref = _revenue_by_source_prefix(db, days=revenue_days)
    rows = db.query(PromoAffiliateLink).order_by(PromoAffiliateLink.id.asc()).all()
    now = datetime.now(timezone.utc)
    out: list[dict[str, Any]] = []
    for row in rows:
        active = _active_row(row, now=now)
        if not include_inactive and not active:
            continue
        dest = _normalize_url(row.url or "")
        short = _normalize_url(row.short_url or "")
        matched: list[ClickLink] = []
        matched.extend(click_idx["by_dest"].get(dest, []))
        if short:
            matched.extend(click_idx["by_dest"].get(short, []))
        lab_slug = _lab_slug(row.label or "")
        lab_ref = _lab_ref(row.label or "")
        slug_prefix = f"aff-{lab_slug}-"
        ref_prefix = f"src_aff_{lab_ref}_"
        for link in click_idx["links"]:
            slug = (link.slug or "").lower()
            ref = (link.source_ref or "").lower()
            if slug.startswith(slug_prefix) or slug == f"aff-{lab_slug}":
                matched.append(link)
            elif ref.startswith(ref_prefix) or ref == f"src_aff_{lab_ref}":
                matched.append(link)
        hits, beacon_details = _sum_hits(matched)
        rev = _match_revenue_for_label(rev_by_ref, label=row.label or "", beacon_details=beacon_details)
        rail = infer_payout_rail(row)
        out.append(
            {
                "id": row.id,
                "label": row.label,
                "url": row.url,
                "short_url": row.short_url,
                "active": active,
                "priority_tier": int(row.priority_tier if row.priority_tier is not None else 99),
                "payout_kind": row.payout_kind,
                "payout_detail": row.payout_detail,
                "payout_rail": rail,
                "placements": row_placements(row),
                "network_keys": row_network_keys(row) or [],
                "copy_template": row.copy_template,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                "clicks": hits,
                "beacon_links": beacon_details,
                "attributed_usd": rev["usd"],
                "attributed_usd_cents": rev["usd_cents"],
                "attributed_entries": rev["entries"],
                "attributed_source_refs": rev["source_refs"],
                "revenue_days": revenue_days,
            }
        )
    out.sort(
        key=lambda r: (
            0 if r["active"] else 1,
            RAIL_SORT_KEY.get(r["payout_rail"], 99),
            int(r["priority_tier"]),
            -int(r["clicks"]),
            int(r["id"]),
        )
    )
    return out


def format_affiliate_sponsor_report_html(
    rows: list[dict[str, Any]],
    *,
    revenue_days: int = 30,
    max_chars: int = 3500,
) -> list[str]:
    """Chunked HTML messages for Telegram DM."""
    total_clicks = sum(int(r["clicks"]) for r in rows)
    total_usd = round(sum(float(r["attributed_usd"]) for r in rows), 2)
    header = (
        f"💰 <b>Affiliate sponsors</b> ({len(rows)} active)\n"
        f"TBCC clicks: <b>{total_clicks}</b> · "
        f"attributed ledger ({revenue_days}d): <b>${total_usd:.2f}</b>\n"
        "<i>Clicks = click-beacon hits when wrap is on. "
        "Attributed $ = income_entries joined by source_ref — "
        "not the affiliate program’s own dashboard balance "
        "(e.g. Cloud Farm USDT wallet must be checked in-app).</i>\n"
    )
    chunks: list[str] = []
    buf = header
    for i, r in enumerate(rows, start=1):
        placements = ", ".join(r["placements"]) or "—"
        nets = ", ".join(r["network_keys"]) or "all"
        detail = (r.get("payout_detail") or "—")
        short = (r.get("short_url") or "").strip()
        url = html.escape(r.get("url") or "")
        label = html.escape(r.get("label") or f"#{r['id']}")
        block_lines = [
            "",
            f"<b>{i}. {label}</b> · id <code>{r['id']}</code> · tier <code>{r['priority_tier']}</code>",
            f"URL: <code>{url}</code>",
        ]
        if short:
            block_lines.append(f"Short: <code>{html.escape(short)}</code>")
        block_lines.extend(
            [
                f"Payout: <code>{html.escape(str(r.get('payout_kind') or ''))}</code> / "
                f"<code>{html.escape(str(detail))}</code> · rail <code>{html.escape(r['payout_rail'])}</code>",
                f"Placements: <code>{html.escape(placements)}</code>",
                f"Networks: <code>{html.escape(nets)}</code>",
                f"Clicks: <b>{int(r['clicks'])}</b>"
                + (
                    f" across {len(r['beacon_links'])} beacon(s)"
                    if r["beacon_links"]
                    else " (no beacon yet — wrap off or never served)"
                ),
                f"Attributed ({revenue_days}d): <b>${float(r['attributed_usd']):.2f}</b> "
                f"· {int(r['attributed_entries'])} ledger entr"
                + ("y" if int(r["attributed_entries"]) == 1 else "ies"),
            ]
        )
        tpl = (r.get("copy_template") or "").strip()
        if tpl:
            block_lines.append(f"Copy: <code>{html.escape(tpl[:120])}</code>")
        block = "\n".join(block_lines)
        if len(buf) + len(block) > max_chars and buf.strip() != header.strip():
            chunks.append(buf.rstrip())
            buf = f"<b>Sponsors</b> <i>(cont.)</i>\n{block}"
        else:
            buf += block
    if buf.strip():
        chunks.append(buf.rstrip())
    return chunks or [header]


def build_affiliate_sponsor_report(
    db: Session,
    *,
    include_inactive: bool = False,
    revenue_days: int = 30,
) -> dict[str, Any]:
    rows = collect_affiliate_sponsor_rows(
        db, include_inactive=include_inactive, revenue_days=revenue_days
    )
    messages = format_affiliate_sponsor_report_html(rows, revenue_days=revenue_days)
    return {
        "ok": True,
        "count": len(rows),
        "revenue_days": revenue_days,
        "rows": rows,
        "messages": messages,
    }
