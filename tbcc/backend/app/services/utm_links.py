"""UTM tagging for AllMyLinks / hub URLs (GA4 attribution)."""

from __future__ import annotations

import os
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_GA4_ID_RE = re.compile(r"^G-[A-Z0-9]+$", re.I)


def utm_enabled() -> bool:
    return (os.getenv("TBCC_UTM_ENABLED") or "1").strip().lower() not in ("0", "false", "no", "off")


def ga4_measurement_id() -> str:
    return (os.getenv("TBCC_GA4_MEASUREMENT_ID") or "").strip()


def slug_utm_value(raw: str | None, *, fallback: str = "hub", max_len: int = 64) -> str:
    s = re.sub(r"[^\w.-]+", "_", (raw or "").strip().lower())
    s = re.sub(r"_+", "_", s).strip("_")
    return (s[:max_len] if s else fallback) or fallback


def append_utm(
    url: str,
    *,
    source: str,
    medium: str,
    campaign: str | None = None,
    content: str | None = None,
    term: str | None = None,
) -> str:
    """Append GA4 UTM query params without duplicating existing keys."""
    base = (url or "").strip()
    if not base or not utm_enabled():
        return base

    parsed = urlparse(base)
    if parsed.scheme not in ("http", "https"):
        return base

    existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params = dict(existing)
    params.setdefault("utm_source", slug_utm_value(source, fallback="aof"))
    params.setdefault("utm_medium", slug_utm_value(medium, fallback="link"))
    if campaign:
        params.setdefault("utm_campaign", slug_utm_value(campaign, fallback="hub"))
    if content:
        params.setdefault("utm_content", slug_utm_value(content, fallback="v1"))
    if term:
        params.setdefault("utm_term", slug_utm_value(term, fallback="hub"))

    new_query = urlencode(params)
    return urlunparse(parsed._replace(query=new_query))


def allmylinks_tracked_url(
    *,
    source: str | None = None,
    medium: str | None = None,
    campaign: str | None = None,
    content: str | None = None,
    term: str | None = None,
    base_url: str | None = None,
) -> str:
    """Return TBCC_ALLMYLINKS_URL with UTM params for GA4 hub analytics."""
    from app.services.aof_social_links import allmylinks_url

    base = (base_url or allmylinks_url() or "").strip()
    if not base:
        return ""
    if not utm_enabled():
        return base

    return append_utm(
        base,
        source=source or (os.getenv("TBCC_UTM_DEFAULT_SOURCE") or "aof"),
        medium=medium or (os.getenv("TBCC_UTM_DEFAULT_MEDIUM") or "link"),
        campaign=campaign or (os.getenv("TBCC_UTM_DEFAULT_CAMPAIGN") or "hub"),
        content=content,
        term=term,
    )
