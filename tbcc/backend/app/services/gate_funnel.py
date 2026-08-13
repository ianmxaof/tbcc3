"""
Gate funnel: beacon click -> funnel touch -> revenue, joined on source_ref.

Deliberately *not* joined on IP. A beacon hit is anonymous and the Telegram
client fetches links from its own infrastructure, so IP matching would invent
conversions that did not happen. The honest join key is the source_ref carried
in the destination's ?start= payload: the same string lands on the click_link,
the user_funnel_touch, and the income_entry.

Crawler hits are excluded from click counts. Telegram link previews and curl
smokes inflate raw hit_count badly enough to make click->touch meaningless.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.click_link import ClickLink, ClickLinkHit
from app.models.user_funnel_touch import UserFunnelTouch
from app.services.click_beacon import derive_source_ref, is_noise_beacon_user_agent

_TELEGRAM_HOSTS = frozenset({"t.me", "telegram.me"})


def _is_telegram_destination(url: str | None) -> bool:
    if not url:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host in _TELEGRAM_HOSTS


def _expects_touch(url: str | None) -> bool:
    """Whether a beacon's destination is even capable of producing a
    user_funnel_touch. Two ways it can't: pointing off-Telegram entirely
    (an affiliate link), or pointing at Telegram but with no ?start=
    payload (a bare bot link — e.g. web-vip/web-spicy's public CTAs).
    record_traffic_touch() only fires from a Telegram /start= payload, so
    either shape produces a real, permanent, *expected* zero — not a
    broken destination.
    """
    if not _is_telegram_destination(url):
        return False
    return derive_source_ref(url or "") is not None


def _pct(numerator: int, denominator: int) -> float | None:
    if not denominator:
        return None
    return round(100.0 * numerator / denominator, 1)


def gate_funnel_report(db: Session, *, days: int = 30) -> dict[str, Any]:
    since = datetime.utcnow() - timedelta(days=max(1, min(366, days)))

    links = db.query(ClickLink).filter(ClickLink.source_ref.isnot(None)).all()
    links_by_ref: dict[str, list[ClickLink]] = {}
    for link in links:
        ref = (link.source_ref or "").strip()
        if ref:
            links_by_ref.setdefault(ref, []).append(link)

    # A ref cannot expect a touch when every beacon registered under it is
    # incapable of carrying a ?start= payload to Telegram — either it points
    # off-Telegram entirely (an affiliate link) or it's a bare Telegram link
    # with no payload (web-vip/web-spicy's public CTAs). Derived from
    # destination_url rather than a hardcoded slug/ref list so new beacons
    # of either shape don't need this function updated to be classified
    # correctly.
    no_touch_expected_refs = {
        ref
        for ref, ref_links in links_by_ref.items()
        if ref_links and all(not _expects_touch(l.destination_url) for l in ref_links)
    }

    link_ids = [int(link.id) for link in links]
    hits: list[ClickLinkHit] = []
    if link_ids:
        hits = (
            db.query(ClickLinkHit)
            .filter(ClickLinkHit.link_id.in_(link_ids), ClickLinkHit.created_at >= since)
            .all()
        )

    ref_by_link_id = {int(link.id): (link.source_ref or "").strip() for link in links}
    clicks: dict[str, int] = {}
    bot_clicks: dict[str, int] = {}
    countries: dict[str, dict[str, int]] = {}
    for hit in hits:
        ref = ref_by_link_id.get(int(hit.link_id))
        if not ref:
            continue
        if is_noise_beacon_user_agent(hit.user_agent):
            bot_clicks[ref] = bot_clicks.get(ref, 0) + 1
            continue
        clicks[ref] = clicks.get(ref, 0) + 1
        country = (hit.country or "").strip().upper()
        if country:
            bucket = countries.setdefault(ref, {})
            bucket[country] = bucket.get(country, 0) + 1

    touch_rows = db.query(UserFunnelTouch).filter(UserFunnelTouch.first_seen_at >= since).all()
    touches: dict[str, int] = {}
    for row in touch_rows:
        ref = (row.first_source_ref or "").strip()
        if ref:
            touches[ref] = touches.get(ref, 0) + 1

    from app.services.traffic_attribution import revenue_by_source

    revenue = revenue_by_source(db, days=days)
    revenue_by_ref = {r["source_ref"]: r for r in revenue.get("revenue_by_source", [])}

    all_refs = set(links_by_ref) | set(clicks) | set(touches) | set(revenue_by_ref)
    rows: list[dict[str, Any]] = []
    for ref in all_refs:
        human_clicks = clicks.get(ref, 0)
        touch_count = touches.get(ref, 0)
        rev = revenue_by_ref.get(ref) or {}
        usd_cents = int(rev.get("usd_cents") or 0)
        top_countries = sorted(
            countries.get(ref, {}).items(),
            key=lambda x: -x[1],
        )[:3]
        rows.append(
            {
                "source_ref": ref,
                "slugs": sorted(link.slug for link in links_by_ref.get(ref, [])),
                "clicks": human_clicks,
                "bot_clicks": bot_clicks.get(ref, 0),
                "touches": touch_count,
                "revenue_usd": round(usd_cents / 100.0, 2),
                "click_to_touch_pct": _pct(touch_count, human_clicks),
                "usd_per_1k_clicks": (
                    round(1000.0 * usd_cents / 100.0 / human_clicks, 2) if human_clicks else None
                ),
                "usd_per_touch": (round(usd_cents / 100.0 / touch_count, 2) if touch_count else None),
                "top_countries": [{"country": c, "clicks": n} for c, n in top_countries],
                # False when this ref structurally cannot produce a touch
                # (affiliate link, or a bare Telegram link with no ?start=
                # payload) — zero touches there is expected, not broken.
                "expects_touch": ref not in no_touch_expected_refs,
            }
        )

    rows.sort(key=lambda r: (-r["revenue_usd"], -r["clicks"]))

    total_clicks = sum(clicks.values())
    total_touches = sum(touches.values())
    return {
        "range_days": days,
        "gate_funnel": rows,
        "totals": {
            "clicks": total_clicks,
            "bot_clicks": sum(bot_clicks.values()),
            "touches": total_touches,
            "click_to_touch_pct": _pct(total_touches, total_clicks),
            "beaconed_source_refs": len(links_by_ref),
        },
        # Refs earning money with no beacon in front of them — unmeasurable spend.
        "unbeaconed_earning_refs": sorted(set(revenue_by_ref) - set(links_by_ref)),
        # Beacons taking clicks that never became a touch — broken destination or
        # a click_only lane gate that cannot carry a start payload. Refs that
        # structurally can't expect a touch (affiliate links, bare Telegram
        # links with no payload) are excluded: zero touches there is correct,
        # not broken (see expects_touch on each row for the same signal,
        # unfiltered).
        "clicks_without_touches": sorted(
            ref
            for ref in clicks
            if clicks[ref] > 0 and touches.get(ref, 0) == 0 and ref not in no_touch_expected_refs
        ),
    }
