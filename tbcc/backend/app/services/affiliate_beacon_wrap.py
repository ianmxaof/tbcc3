"""Wrap affiliate outbound URLs in TBCC click beacons for measurable passthrough."""

from __future__ import annotations

import logging
import os
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.orm import Session

from app.models.click_link import ClickLink
from app.models.promo_affiliate_link import PromoAffiliateLink
from app.services.click_beacon import create_click_link, link_public_url, validate_destination_url

logger = logging.getLogger(__name__)

_SLUG_SAFE = re.compile(r"[^a-z0-9]+")


def affiliate_beacon_wrap_enabled() -> bool:
    return (os.getenv("TBCC_AFFILIATE_BEACON_WRAP") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _slug_for_affiliate(label: str, placement: str) -> str:
    lab = _SLUG_SAFE.sub("-", (label or "aff").lower()).strip("-")[:14] or "aff"
    pl = _SLUG_SAFE.sub("-", (placement or "slot").lower()).strip("-")[:10] or "slot"
    slug = f"aff-{lab}-{pl}"
    return slug[:32]


def _source_ref_for_affiliate(label: str, placement: str) -> str:
    lab = _SLUG_SAFE.sub("_", (label or "aff").lower()).strip("_")[:24] or "aff"
    pl = _SLUG_SAFE.sub("_", (placement or "slot").lower()).strip("_")[:16] or "slot"
    ref = f"src_aff_{lab}_{pl}"
    return ref[:56]


_TELEGRAM_DEEPLINK_HOSTS = frozenset({"t.me", "telegram.me", "telegram.dog"})


def _rewrite_attribution_start_param(url: str, source_ref: str) -> str:
    """
    Point owned-bot deep links at the placement-specific beacon ref so
    click → /start touch → revenue all join on one source_ref.

    Only rewrites `start` payloads that are already pure attribution markers
    (`src_*`); product payloads like `loot_free` keep their behavior.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if (parts.hostname or "").lower() not in _TELEGRAM_DEEPLINK_HOSTS:
        return url
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    changed = False
    out: list[tuple[str, str]] = []
    for key, value in pairs:
        if key == "start" and value.startswith("src_") and value != source_ref:
            out.append((key, source_ref))
            changed = True
        else:
            out.append((key, value))
    if not changed:
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(out), parts.fragment))


def get_or_create_affiliate_beacon(
    db: Session,
    *,
    destination_url: str,
    label: str,
    placement: str,
) -> ClickLink:
    slug = _slug_for_affiliate(label, placement)
    source_ref = _source_ref_for_affiliate(label, placement)
    dest = validate_destination_url(
        _rewrite_attribution_start_param(destination_url, source_ref)
    )
    row = db.query(ClickLink).filter(ClickLink.slug == slug).first()
    if row:
        if row.destination_url != dest:
            row.destination_url = dest
            if not row.source_ref:
                row.source_ref = source_ref
            db.commit()
            db.refresh(row)
        return row
    try:
        return create_click_link(
            db,
            destination_url=dest,
            label=f"{label} · {placement}",
            slug=slug,
            source_ref=source_ref,
        )
    except ValueError as e:
        if "slug_taken" not in str(e):
            raise
        row = db.query(ClickLink).filter(ClickLink.slug == slug).first()
        if row:
            return row
        raise


def wrap_affiliate_outbound_url(
    db: Session | None,
    row: PromoAffiliateLink,
    *,
    placement: str,
    raw_url: str | None = None,
) -> str:
    url = (raw_url or (row.short_url or row.url or "")).strip()
    if not url or db is None or not affiliate_beacon_wrap_enabled():
        return url
    try:
        link = get_or_create_affiliate_beacon(
            db,
            destination_url=url,
            label=(row.label or "affiliate").strip(),
            placement=placement,
        )
        return link_public_url(link)
    except Exception as e:
        logger.debug("affiliate beacon wrap failed: %s", e)
        return url


def wrap_companion_affiliate_url(db: Session, raw_url: str, *, placement: str = "companion_dm") -> str:
    """Beacon-wrap companion DM undress affiliate links for measurable passthrough."""
    url = (raw_url or "").strip()
    if not url or not affiliate_beacon_wrap_enabled():
        return url
    try:
        link = get_or_create_affiliate_beacon(
            db,
            destination_url=url,
            label="Undress AI bot",
            placement=placement,
        )
        return link_public_url(link)
    except Exception as e:
        logger.debug("companion affiliate beacon wrap failed: %s", e)
        return url
