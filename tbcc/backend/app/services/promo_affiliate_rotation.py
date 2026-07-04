"""Pick and format promo affiliate links for rotation across AOF surfaces."""

from __future__ import annotations

import html
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import asc
from sqlalchemy.orm import Session

from app.models.promo_affiliate_link import PromoAffiliateLink
from app.models.promo_affiliate_rotation_cursor import PromoAffiliateRotationCursor

logger = logging.getLogger(__name__)

AFFILIATE_PLACEMENTS: frozenset[str] = frozenset(
    {"manual_only", "x_buffer", "telegram_footer", "links_hub", "links_hub_ai"}
)
DEFAULT_PLACEMENT = "manual_only"


@dataclass(frozen=True)
class AffiliatePick:
    row: PromoAffiliateLink
    placement: str
    network_key: str | None
    slot_index: int


def _parse_json_list(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data:
        s = str(item or "").strip().lower()
        if s and s not in out:
            out.append(s)
    return out


def row_placements(row: PromoAffiliateLink) -> list[str]:
    vals = _parse_json_list(getattr(row, "placements_json", None))
    if not vals:
        return [DEFAULT_PLACEMENT]
    return [p for p in vals if p in AFFILIATE_PLACEMENTS] or [DEFAULT_PLACEMENT]


def row_network_keys(row: PromoAffiliateLink) -> list[str] | None:
    vals = _parse_json_list(getattr(row, "network_keys_json", None))
    return vals if vals else None


def _row_active(row: PromoAffiliateLink) -> bool:
    if not bool(row.active):
        return False
    exp = row.expires_at
    if exp is not None:
        now = datetime.now(timezone.utc)
        exp_utc = exp.replace(tzinfo=timezone.utc) if exp.tzinfo is None else exp
        if exp_utc <= now:
            return False
    return True


def _matches_network(row: PromoAffiliateLink, network_key: str | None) -> bool:
    keys = row_network_keys(row)
    if not keys:
        return True
    if not network_key:
        return True
    nk = network_key.strip().lower()
    return nk in keys


def list_candidates(
    db: Session,
    placement: str,
    *,
    network_key: str | None = None,
    exclude_manual_only: bool = True,
) -> list[PromoAffiliateLink]:
    placement = (placement or "").strip().lower()
    rows = (
        db.query(PromoAffiliateLink)
        .filter(PromoAffiliateLink.active.is_(True))
        .order_by(asc(PromoAffiliateLink.priority_tier), asc(PromoAffiliateLink.id))
        .all()
    )
    out: list[PromoAffiliateLink] = []
    for row in rows:
        if not _row_active(row):
            continue
        placements = row_placements(row)
        if placement not in placements:
            continue
        if exclude_manual_only and placement != "manual_only" and placements == [DEFAULT_PLACEMENT]:
            continue
        if not _matches_network(row, network_key):
            continue
        out.append(row)
    return out


def _cursor_key(placement: str, network_key: str | None) -> tuple[str, str]:
    return (placement.strip().lower(), (network_key or "").strip().lower())


def _get_cursor(db: Session, placement: str, network_key: str | None) -> PromoAffiliateRotationCursor:
    p, nk = _cursor_key(placement, network_key)
    row = (
        db.query(PromoAffiliateRotationCursor)
        .filter(
            PromoAffiliateRotationCursor.placement == p,
            PromoAffiliateRotationCursor.network_key == nk,
        )
        .first()
    )
    if row:
        return row
    row = PromoAffiliateRotationCursor(placement=p, network_key=nk, cursor_index=0)
    db.add(row)
    db.flush()
    return row


def affiliate_outbound_url(row: PromoAffiliateLink) -> str:
    short = (row.short_url or "").strip()
    if short:
        return short
    return (row.url or "").strip()


def build_sponsor_link_html(row: PromoAffiliateLink, *, anchor: str | None = None) -> str:
    from app.services.aof_growth_hub import _a_tag

    url = affiliate_outbound_url(row)
    label = (anchor or row.label or "Sponsor").strip()
    link = _a_tag(url, label)
    template = (getattr(row, "copy_template", None) or "").strip() or "💰 {link}"
    return (
        template.replace("{link}", link)
        .replace("{url}", html.escape(url, quote=True))
        .replace("{label}", html.escape(label))
    )


def build_sponsor_line_plain(row: PromoAffiliateLink) -> str:
    url = affiliate_outbound_url(row)
    label = (row.label or "Sponsor").strip()
    template = (getattr(row, "copy_template", None) or "").strip()
    if template:
        plain = template.replace("{link}", url).replace("{url}", url).replace("{label}", label)
        if "<" not in plain:
            return plain
    return f"{label}: {url}"


def pick_affiliate(
    db: Session,
    placement: str,
    *,
    network_key: str | None = None,
    advance: bool = True,
) -> AffiliatePick | None:
    candidates = list_candidates(db, placement, network_key=network_key)
    if not candidates:
        return None
    cur = _get_cursor(db, placement, network_key)
    idx = int(cur.cursor_index or 0) % len(candidates)
    pick = AffiliatePick(row=candidates[idx], placement=placement, network_key=network_key, slot_index=idx)
    if advance:
        cur.cursor_index = (idx + 1) % len(candidates)
        cur.updated_at = datetime.utcnow()
    return pick


def preview_affiliates(
    db: Session,
    placement: str,
    *,
    network_key: str | None = None,
    count: int = 5,
) -> list[dict[str, Any]]:
    candidates = list_candidates(db, placement, network_key=network_key)
    if not candidates:
        return []
    cur = _get_cursor(db, placement, network_key)
    start = int(cur.cursor_index or 0) % len(candidates)
    n = max(1, min(20, int(count)))
    out: list[dict[str, Any]] = []
    for i in range(min(n, len(candidates))):
        row = candidates[(start + i) % len(candidates)]
        out.append(
            {
                "id": row.id,
                "label": row.label,
                "url": affiliate_outbound_url(row),
                "priority_tier": row.priority_tier,
                "line_html": build_sponsor_link_html(row),
                "line_plain": build_sponsor_line_plain(row),
            }
        )
    return out


def affiliate_rotation_stats(db: Session) -> dict[str, Any]:
    rows = db.query(PromoAffiliateLink).filter(PromoAffiliateLink.active.is_(True)).all()
    by_placement: dict[str, int] = {p: 0 for p in sorted(AFFILIATE_PLACEMENTS)}
    for row in rows:
        if not _row_active(row):
            continue
        for p in row_placements(row):
            by_placement[p] = by_placement.get(p, 0) + 1
    return {
        "active_rows": sum(1 for r in rows if _row_active(r)),
        "by_placement": by_placement,
        "cursors": db.query(PromoAffiliateRotationCursor).count(),
    }


def resolve_affiliate_url(
    db: Session | None,
    placement: str,
    *,
    network_key: str | None = None,
    advance: bool = False,
    fallback: str | None = None,
) -> str:
    if db is not None:
        pick = pick_affiliate(db, placement, network_key=network_key, advance=advance)
        if pick:
            return affiliate_outbound_url(pick.row)
    elif fallback is None:
        from app.database.session import SessionLocal

        local = SessionLocal()
        try:
            pick = pick_affiliate(local, placement, network_key=network_key, advance=advance)
            if pick:
                if advance:
                    local.commit()
                return affiliate_outbound_url(pick.row)
        finally:
            local.close()
    if fallback:
        return fallback
    from app.services.aof_social_links import affiliate_undress_primary_url

    return affiliate_undress_primary_url()
