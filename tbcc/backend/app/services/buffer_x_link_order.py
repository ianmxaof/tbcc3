"""Deterministic first-URL rotation for Buffer / X captions (link preview cards)."""

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_PLACEMENT = "x_link_first"
_URL_RE = re.compile(r"https://[^\s<>\"'\)]+", re.I)
_GUMROAD_RE = re.compile(r"gumroad\.com/l/", re.I)
_AFFILIATE_RE = re.compile(
    r"nodress|nudify\.now|musebox|playbun|fapify|drawai|botynude|/ref/|bot\?username=",
    re.I,
)
_TELEGRAM_RE = re.compile(r"t\.me/", re.I)
_ALLMYLINKS_RE = re.compile(r"allmylinks\.com", re.I)
_EROME_RE = re.compile(r"erome\.com", re.I)
_GRAVATAR_RE = re.compile(r"gravatar\.com", re.I)
_PROMO_VIEWER_RE = re.compile(r"ibb\.co/(?!.+\.(jpg|jpeg|png|gif|webp)$)|imgbb\.com/album", re.I)

CATEGORY_ORDER: tuple[str, ...] = (
    "affiliate",
    "gumroad_vip",
    "allmylinks",
    "erome",
    "promo_viewer",
    "telegram",
    "gravatar",
    "other",
)


def link_cycle_enabled() -> bool:
    return (os.getenv("TBCC_BUFFER_X_LINK_CYCLE") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def affiliate_first_enabled() -> bool:
    """
    Hard-pin affiliate URL first for X link previews.

    Default ON — cycling telegram/allmylinks into first position made X show
    the Telegram globe card instead of Undress/SFW affiliate creatives.
    Set TBCC_BUFFER_X_AFFILIATE_FIRST=0 to restore category cycling.
    """
    return (os.getenv("TBCC_BUFFER_X_AFFILIATE_FIRST") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def classify_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return "other"
    if _GUMROAD_RE.search(u):
        return "gumroad_vip"
    if _AFFILIATE_RE.search(u):
        return "affiliate"
    if _EROME_RE.search(u):
        return "erome"
    if _ALLMYLINKS_RE.search(u):
        return "allmylinks"
    if _PROMO_VIEWER_RE.search(u):
        return "promo_viewer"
    if _GRAVATAR_RE.search(u):
        return "gravatar"
    if _TELEGRAM_RE.search(u):
        return "telegram"
    return "other"


def _strip_url_trail(url: str) -> str:
    return url.rstrip(".,;)")


def _url_separator(text: str, matches: list[re.Match[str]]) -> str:
    if len(matches) < 2:
        return " "
    between = text[matches[0].end() : matches[1].start()]
    if "\n" in between:
        return "\n"
    if " · " in between:
        return " · "
    if " ·" in between or "· " in between:
        return " · "
    return " "


def _ordered_categories(urls: list[str]) -> list[str]:
    present: set[str] = set()
    for url in urls:
        present.add(classify_url(url))
    return [c for c in CATEGORY_ORDER if c in present]


def _pick_first_category(db: Session, categories: list[str], *, advance: bool) -> str | None:
    if not categories:
        return None
    from app.models.promo_affiliate_rotation_cursor import PromoAffiliateRotationCursor

    row = (
        db.query(PromoAffiliateRotationCursor)
        .filter(
            PromoAffiliateRotationCursor.placement == _PLACEMENT,
            PromoAffiliateRotationCursor.network_key == "",
        )
        .first()
    )
    if row is None:
        row = PromoAffiliateRotationCursor(placement=_PLACEMENT, network_key="", cursor_index=0)
        db.add(row)
        db.flush()
    idx = int(row.cursor_index or 0) % len(categories)
    chosen = categories[idx]
    if advance:
        row.cursor_index = (idx + 1) % len(categories)
    return chosen


def reorder_caption_urls(text: str, first_category: str) -> str:
    """Move the first URL of ``first_category`` to the front of the URL block."""
    raw = (text or "").strip()
    if not raw:
        return raw
    matches = list(_URL_RE.finditer(raw))
    if len(matches) < 2:
        return raw

    urls = [_strip_url_trail(m.group(0)) for m in matches]
    cats = [classify_url(u) for u in urls]
    if first_category not in cats:
        return raw

    idx = cats.index(first_category)
    if idx == 0:
        return raw

    prose = raw[: matches[0].start()].rstrip()
    sep = _url_separator(raw, matches)
    ordered = urls[idx:] + urls[:idx]
    url_block = sep.join(ordered)
    if prose:
        joiner = sep if sep == "\n" else " "
        return f"{prose}{joiner}{url_block}"
    return url_block


def apply_buffer_x_link_cycle(
    text: str,
    db: Session | None = None,
    *,
    advance: bool = False,
) -> str:
    """
    Order URLs for X link previews.

    Default: affiliate first when present (never bare t.me as the card).
    Optional cycle (TBCC_BUFFER_X_AFFILIATE_FIRST=0 + LINK_CYCLE=1) rotates
    among affiliate / hub / erome / telegram.
    """
    raw = (text or "").strip()
    if not raw:
        return raw
    matches = list(_URL_RE.finditer(raw))
    if len(matches) < 2:
        return raw

    urls = [_strip_url_trail(m.group(0)) for m in matches]
    categories = _ordered_categories(urls)

    if affiliate_first_enabled() and "affiliate" in categories:
        return reorder_caption_urls(raw, "affiliate")

    if not link_cycle_enabled():
        return raw
    if len(categories) < 2:
        return raw

    if db is None:
        from app.database.session import SessionLocal

        local = SessionLocal()
        try:
            first = _pick_first_category(local, categories, advance=advance)
            out = reorder_caption_urls(raw, first) if first else raw
            if advance:
                local.commit()
            return out
        finally:
            local.close()

    first = _pick_first_category(db, categories, advance=advance)
    if not first:
        return raw
    return reorder_caption_urls(raw, first)


def first_url(text: str) -> str | None:
    m = _URL_RE.search(text or "")
    return _strip_url_trail(m.group(0)) if m else None
