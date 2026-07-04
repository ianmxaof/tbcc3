"""Rotating captions + affiliate footers for SENT CACHE album exports."""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_network import network_channel_by_key
from app.models.caption_snippet import CaptionSnippet
from app.services.aof_copy_swipe import _SWIPE_TITLE_PREFIX
from app.services.aof_growth_hub import build_addlist_footer, gate_urls
from app.services.promo_affiliate_rotation import build_sponsor_link_html, pick_affiliate
from app.services.storage_sent_cache import sent_cache_caption

logger = logging.getLogger(__name__)

REDIS_CAPTION_CURSOR = "tbcc:sent_cache_composer:caption_cursor:"


def _redis():
    from app.services.content_signals import _redis_client

    return _redis_client()


def _snippet_lane_keys(network_key: str) -> tuple[str, ...]:
    nk = (network_key or "").strip().lower()
    lanes: list[str] = []
    if nk:
        lanes.append(nk)
    lanes.extend(["main_group_pulse", "telegram_native"])
    out: list[str] = []
    for lane in lanes:
        if lane not in out:
            out.append(lane)
    return tuple(out)


def _caption_candidates(db: Session, network_key: str) -> list[CaptionSnippet]:
    prefixes = tuple(f"{_SWIPE_TITLE_PREFIX}{lane}:" for lane in _snippet_lane_keys(network_key))
    rows = db.query(CaptionSnippet).order_by(CaptionSnippet.id.asc()).all()
    out: list[CaptionSnippet] = []
    for row in rows:
        title = (row.title or "").strip()
        if any(title.startswith(p) for p in prefixes):
            out.append(row)
    if out:
        return out
    # Fallback: any swipe-promoted snippets
    return [r for r in rows if (r.title or "").startswith(_SWIPE_TITLE_PREFIX)]


def pick_rotated_caption_body(db: Session, network_key: str) -> str:
    """Next caption body from copy-ingestion RAG (caption_snippets / swipe promotions)."""
    candidates = _caption_candidates(db, network_key)
    if not candidates:
        net = network_channel_by_key(network_key)
        if net and net.promo_html:
            return net.promo_html.strip()
        return ""

    nk = (network_key or "").strip().lower() or "lane"
    idx = 0
    try:
        r = _redis()
        raw = r.get(f"{REDIS_CAPTION_CURSOR}{nk}")
        if raw is not None:
            idx = int(raw)
    except Exception:
        pass
    row = candidates[idx % len(candidates)]
    try:
        r = _redis()
        r.set(f"{REDIS_CAPTION_CURSOR}{nk}", str((idx + 1) % max(1, len(candidates))))
    except Exception:
        pass
    return (row.body or "").strip()


def build_affiliate_footer_html(db: Session, network_key: str) -> str:
    lv = gate_urls(db)
    pick = pick_affiliate(db, "telegram_footer", network_key=network_key, advance=True)
    sponsor = build_sponsor_link_html(pick.row) if pick and pick.row else None
    return build_addlist_footer(lv, sponsor_line_html=sponsor)


def build_cache_album_caption_html(db: Session, network_key: str) -> str:
    """Stamp + rotated swipe copy + affiliate footer for cache / main-group albums."""
    stamp = sent_cache_caption(network_key)
    body = pick_rotated_caption_body(db, network_key)
    footer = build_affiliate_footer_html(db, network_key)
    parts = [stamp]
    if body:
        parts.append(body)
    if footer:
        parts.append(footer)
    return "\n\n".join(parts).strip()


def build_main_group_caption_html(db: Session, network_key: str) -> str:
    """Main-group variant — no duplicate stamp line (album is the content)."""
    body = pick_rotated_caption_body(db, network_key)
    footer = build_affiliate_footer_html(db, network_key)
    parts = [p for p in (body, footer) if p]
    return "\n\n".join(parts).strip() if parts else build_cache_album_caption_html(db, network_key)
