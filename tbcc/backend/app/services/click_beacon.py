"""Promo click beacon — create short links, record hits, notify admin (no GPS)."""

from __future__ import annotations

import logging
import os
import re
import secrets
import time
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.click_link import ClickLink, ClickLinkHit

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"^[A-Za-z0-9_-]{4,32}$")
_ip_hits: dict[str, list[float]] = {}
_notify_dedupe: dict[tuple[str, str], float] = {}
_RATE_WINDOW_S = 60.0
_RATE_MAX = 30
_NOTIFY_DEDUPE_S = 900.0  # 15 min — same slug+ip

_NOISE_UA_MARKERS = (
    "curl/",
    "telegrambot",
    "like twitterbot",
    "headlesschrome",
    "python-requests",
    "go-http-client",
    "wget/",
    "httpie/",
)


def public_beacon_base() -> str:
    raw = (
        (os.getenv("TBCC_CLICK_BEACON_PUBLIC_BASE") or "").strip()
        or (os.getenv("TBCC_API_PUBLIC_URL") or "").strip()
        or "http://127.0.0.1:8000"
    )
    return raw.rstrip("/")


def click_beacon_notify_enabled() -> bool:
    return (os.getenv("TBCC_CLICK_BEACON_NOTIFY") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def click_beacon_instant_telegram() -> bool:
    """Instant DM on beacon hit — default off (inbox only); smokes/crawlers spam otherwise."""
    return (os.getenv("TBCC_CLICK_BEACON_INSTANT") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def click_beacon_notify_bots() -> bool:
    return (os.getenv("TBCC_CLICK_BEACON_NOTIFY_BOTS") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def is_noise_beacon_user_agent(user_agent: str | None) -> bool:
    ua = (user_agent or "").strip().lower()
    if not ua:
        return False
    return any(marker in ua for marker in _NOISE_UA_MARKERS)


def should_notify_beacon_hit(link: ClickLink, hit: ClickLinkHit) -> bool:
    if not click_beacon_notify_enabled():
        return False
    if is_noise_beacon_user_agent(hit.user_agent) and not click_beacon_notify_bots():
        return False
    ip = (hit.ip or "").strip() or "unknown"
    key = (str(link.slug), ip)
    now = time.monotonic()
    last = _notify_dedupe.get(key)
    if last is not None and (now - last) < _NOTIFY_DEDUPE_S:
        return False
    _notify_dedupe[key] = now
    return True


def validate_destination_url(url: str) -> str:
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        raise ValueError("destination must be http(s)")
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("invalid destination url")
    if parsed.scheme == "javascript":
        raise ValueError("javascript urls blocked")
    return u[:2048]


def _new_slug() -> str:
    return secrets.token_urlsafe(9)[:12]


def create_click_link(
    db: Session,
    *,
    destination_url: str,
    label: str | None = None,
    slug: str | None = None,
) -> ClickLink:
    dest = validate_destination_url(destination_url)
    s = (slug or "").strip() or _new_slug()
    if not _SLUG_RE.match(s):
        raise ValueError("slug must be 4-32 chars [A-Za-z0-9_-]")
    if db.query(ClickLink).filter(ClickLink.slug == s).first():
        raise ValueError("slug_taken")
    row = ClickLink(
        slug=s,
        destination_url=dest,
        label=(label or "").strip()[:128] or None,
        active=1,
        hit_count=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_click_links(db: Session, *, limit: int = 50) -> list[ClickLink]:
    return (
        db.query(ClickLink)
        .order_by(ClickLink.id.desc())
        .limit(max(1, min(int(limit), 200)))
        .all()
    )


def get_by_slug(db: Session, slug: str) -> ClickLink | None:
    s = (slug or "").strip()
    if not s:
        return None
    return db.query(ClickLink).filter(ClickLink.slug == s, ClickLink.active == 1).one_or_none()


def rate_limit_ip(ip: str) -> bool:
    """Return True if allowed."""
    key = (ip or "unknown").strip() or "unknown"
    now = time.monotonic()
    bucket = [t for t in _ip_hits.get(key, []) if now - t < _RATE_WINDOW_S]
    if len(bucket) >= _RATE_MAX:
        _ip_hits[key] = bucket
        return False
    bucket.append(now)
    _ip_hits[key] = bucket
    return True


def record_hit(
    db: Session,
    link: ClickLink,
    *,
    ip: str | None,
    user_agent: str | None,
    referer: str | None,
    country: str | None,
    campaign_id: str | None,
) -> ClickLinkHit:
    hit = ClickLinkHit(
        link_id=int(link.id),
        campaign_id=(campaign_id or "").strip()[:128] or None,
        ip=(ip or "").strip()[:64] or None,
        user_agent=(user_agent or "").strip()[:512] or None,
        referer=(referer or "").strip()[:512] or None,
        country=(country or "").strip()[:8] or None,
    )
    link.hit_count = int(link.hit_count or 0) + 1
    db.add(hit)
    db.commit()
    db.refresh(hit)
    return hit


def notify_admin_click(link: ClickLink, hit: ClickLinkHit) -> None:
    if not should_notify_beacon_hit(link, hit):
        return
    try:
        from app.services.admin_inbox import push_admin_inbox_event

        label = (link.label or link.slug).strip()
        push_admin_inbox_event(
            category="growth",
            severity="info",
            title=f"Click beacon · {label}",
            body="",
            meta={
                "slug": link.slug,
                "hit_count": int(link.hit_count or 0),
                "hit_id": hit.id,
                "ip": hit.ip,
                "country": hit.country,
                "user_agent": hit.user_agent,
                "campaign_id": hit.campaign_id,
                "destination_url": link.destination_url,
            },
            instant=click_beacon_instant_telegram(),
        )
    except Exception as e:
        logger.warning("click beacon notify failed: %s", e)


def link_public_url(link: ClickLink) -> str:
    return f"{public_beacon_base()}/r/{link.slug}"


def link_as_dict(link: ClickLink) -> dict[str, Any]:
    return {
        "id": link.id,
        "slug": link.slug,
        "destination_url": link.destination_url,
        "label": link.label,
        "active": bool(link.active),
        "hit_count": int(link.hit_count or 0),
        "public_url": link_public_url(link),
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }
