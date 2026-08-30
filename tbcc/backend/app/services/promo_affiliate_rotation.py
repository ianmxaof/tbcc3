"""Pick and format promo affiliate links for rotation across AOF surfaces."""

from __future__ import annotations

import html
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import asc
from sqlalchemy.orm import Session

from app.models.promo_affiliate_link import PromoAffiliateLink
from app.models.promo_affiliate_rotation_cursor import PromoAffiliateRotationCursor
from app.services.affiliate_payout_rail import affiliate_sort_key, infer_payout_rail

logger = logging.getLogger(__name__)


def spicy_bias_every() -> int:
    """
    On x_buffer, force the owned Spicy Companion row every Nth advance.
    0 disables. Default 3 — conversion was starved at 0 spicy clicks / 30d.
    """
    raw = (os.getenv("TBCC_BUFFER_X_SPICY_BIAS_EVERY") or "3").strip()
    try:
        return max(0, min(20, int(raw)))
    except ValueError:
        return 3


def is_spicy_companion_row(row: PromoAffiliateLink) -> bool:
    label = (getattr(row, "label", None) or "").strip().lower()
    url = (getattr(row, "url", None) or "").strip().lower()
    if "aof_spicybot" in url or "spicy companion" in label:
        return True
    return "spicy" in label and ("telegram.me" in url or "t.me" in url)

AFFILIATE_PLACEMENTS: frozenset[str] = frozenset(
    {
        "manual_only",
        "x_buffer",
        "telegram_footer",
        "links_hub",
        "links_hub_ai",
        "links_hub_sfw",
        "loot_roll",
        "bot_network_menu",
    }
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
    out.sort(key=affiliate_sort_key)
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


def affiliate_outbound_url(row: PromoAffiliateLink, db: Session | None = None, placement: str = "") -> str:
    short = (row.short_url or "").strip()
    raw = short or (row.url or "").strip()
    if db is not None and placement:
        from app.services.affiliate_beacon_wrap import wrap_affiliate_outbound_url

        return wrap_affiliate_outbound_url(db, row, placement=placement, raw_url=raw)
    return raw


def build_sponsor_link_html(
    row: PromoAffiliateLink, *, anchor: str | None = None, db: Session | None = None, placement: str = ""
) -> str:
    from app.services.aof_growth_hub import _a_tag

    url = affiliate_outbound_url(row, db=db, placement=placement)
    label = (anchor or row.label or "Sponsor").strip()
    link = _a_tag(url, label)
    template = (getattr(row, "copy_template", None) or "").strip() or "💰 {link}"
    return (
        template.replace("{link}", link)
        .replace("{url}", html.escape(url, quote=True))
        .replace("{label}", html.escape(label))
    )


def build_sponsor_line_plain(
    row: PromoAffiliateLink, *, db: Session | None = None, placement: str = ""
) -> str:
    url = affiliate_outbound_url(row, db=db, placement=placement)
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
    placement_norm = (placement or "").strip().lower()
    pack_pick: AffiliatePick | None = None
    try:
        from app.services.affiliate_sponsor_pack_pick import pick_from_sponsor_pack

        pack_pick = pick_from_sponsor_pack(
            db, placement_norm, network_key=network_key, advance=advance
        )
    except Exception:
        logger.debug("sponsor pack pick skipped", exc_info=True)
        pack_pick = None

    if pack_pick is not None:
        pick = pack_pick
    else:
        candidates = list_candidates(db, placement, network_key=network_key)
        if not candidates:
            return None
        cur = _get_cursor(db, placement, network_key)
        idx = int(cur.cursor_index or 0) % len(candidates)
        every = spicy_bias_every()
        # Spicy bias only on legacy (non-pack) x_buffer rotation — Pack B owns Companion closes.
        if (
            placement_norm == "x_buffer"
            and every > 0
            and advance
            and idx % every == 0
        ):
            for i, row in enumerate(candidates):
                if is_spicy_companion_row(row):
                    idx = i
                    break
        pick = AffiliatePick(
            row=candidates[idx], placement=placement, network_key=network_key, slot_index=idx
        )
        if advance:
            # Advance from the natural cursor slot, not the forced spicy index,
            # so bias injects without collapsing the rest of the rotation.
            natural = int(cur.cursor_index or 0) % len(candidates)
            cur.cursor_index = (natural + 1) % len(candidates)
            cur.updated_at = datetime.utcnow()

    if advance and pick is not None:
        try:
            from app.services.affiliate_beacon_wrap import _source_ref_for_affiliate
            from app.services.traffic_pulse import pulse_affiliate_served

            out_url = affiliate_outbound_url(pick.row, db=db, placement=placement_norm)
            pulse_affiliate_served(
                placement=placement_norm,
                label=(pick.row.label or "affiliate").strip(),
                url=out_url,
                source_ref=_source_ref_for_affiliate(pick.row.label or "aff", placement_norm),
            )
        except Exception:
            logger.debug("affiliate served pulse skipped", exc_info=True)
    return pick


def resolve_spicy_companion_url(
    db: Session | None = None,
    *,
    placement: str = "x_buffer",
) -> str:
    """Beacon-wrapped spicy companion URL when seeded; else attributed deep link."""
    from app.services.aof_social_links import companion_bot_username

    uname = companion_bot_username()
    fallback = f"https://telegram.me/{uname}?start=src_spicy_x" if uname else ""
    if db is None:
        return fallback
    for row in list_candidates(db, placement):
        if is_spicy_companion_row(row):
            return affiliate_outbound_url(row, db=db, placement=placement)
    return fallback


def pick_affiliate_pair(
    db: Session,
    placement: str,
    *,
    network_key: str | None = None,
    advance: bool = False,
) -> tuple[str, str]:
    """Two distinct outbound URLs from the placement rotation (wraps on pool size)."""
    from app.services.aof_social_links import affiliate_primary_fallback_url

    fallback = affiliate_primary_fallback_url()
    candidates = list_candidates(db, placement, network_key=network_key)
    if not candidates:
        return fallback, fallback
    cur = _get_cursor(db, placement, network_key)
    idx = int(cur.cursor_index or 0) % len(candidates)
    url1 = affiliate_outbound_url(candidates[idx], db=db, placement=placement)
    url2 = affiliate_outbound_url(candidates[(idx + 1) % len(candidates)], db=db, placement=placement)
    if url1 == url2 and len(candidates) > 2:
        url2 = affiliate_outbound_url(candidates[(idx + 2) % len(candidates)], db=db, placement=placement)
    if advance:
        cur.cursor_index = (idx + 1) % len(candidates)
        cur.updated_at = datetime.utcnow()
    return url1, url2


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
                return affiliate_outbound_url(pick.row, db=local, placement=placement)
        finally:
            local.close()
    if fallback:
        return fallback
    from app.services.aof_social_links import affiliate_primary_fallback_url

    return affiliate_primary_fallback_url()


def build_loot_roll_affiliate_footer_html(
    db: Session,
    *,
    advance: bool = True,
    network_key: str | None = None,
) -> str | None:
    """
    Small italic footer for paid roll album captions.
    Prefers placement=loot_roll, falls back to telegram_footer.
    Hyperlink sits inside a short sentence (or uses copy_template when set).
    """
    pick = pick_affiliate(db, "loot_roll", network_key=network_key, advance=advance)
    if not pick:
        pick = pick_affiliate(db, "telegram_footer", network_key=network_key, advance=advance)
    if not pick:
        return None
    row = pick.row
    pl = pick.placement
    template = (getattr(row, "copy_template", None) or "").strip()
    if template and ("{link}" in template or "{url}" in template):
        line = build_sponsor_link_html(row, db=db, placement=pl)
        return f"<i>{line}</i>" if not line.lower().startswith("<i>") else line
    from app.services.aof_growth_hub import _a_tag

    url = affiliate_outbound_url(row, db=db, placement=pl)
    if not url:
        return None
    word = (row.label or "here").strip().split()[0][:28] or "here"
    return f"<i>Partner tip — tap {_a_tag(url, word)}</i>"
